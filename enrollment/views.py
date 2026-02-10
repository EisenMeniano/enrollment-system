from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from accounts.models import User, StudentProfile
from accounts.forms import PersonalDetailsUserForm, PersonalDetailsProfileForm, AddressDetailsForm, CourseDetailsForm
from .models import Enlistment, HistoryLog, EnlistmentSubject, Subject, EnrollmentWindow
from .forms import EnlistmentCreateForm, ReturnReasonForm, SubjectSelectForm, PaymentForm, FinanceAmountForm, StudentSubjectSelectForm
from .services import (
    student_submit_enlistment,
    adviser_preapprove,
    adviser_return_for_revision,
    finance_review,
    adviser_final_approve_and_add_subjects,
    student_mark_paid,
    finance_set_amount,
)

def role_required(*roles):
    def decorator(view_func):
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated or request.user.role not in roles:
                raise PermissionDenied("You do not have access to this page.")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator

@login_required
def dashboard(request):
    if request.user.role == User.Role.STUDENT:
        return redirect("enrollment:student_dashboard")
    if request.user.role == User.Role.ADVISER:
        return redirect("enrollment:adviser_dashboard")
    if request.user.role == User.Role.FINANCE:
        return redirect("enrollment:finance_dashboard")
    return redirect("accounts:login")

# ---------------------- STUDENT ----------------------
@login_required
@role_required("STUDENT")
def student_dashboard(request):
    return redirect("enrollment:student_profile_personal")

@login_required
@role_required("STUDENT")
def student_enlistment_create(request):
    window = EnrollmentWindow.get_solo()
    if not window.is_open:
        return render(
            request,
            "enrollment/enrollment_closed.html",
            {"message": window.message or "Enrollment is currently closed."},
        )
    if request.method == "POST":
        form = EnlistmentCreateForm(request.POST)
        if form.is_valid():
            try:
                enlistment = student_submit_enlistment(
                    request.user,
                    category=form.cleaned_data["category"],
                    program=form.cleaned_data["program"],
                    school_year=form.cleaned_data["school_year"].label,
                    semester=form.cleaned_data["semester"].name,
                    notes=form.cleaned_data.get("notes", ""),
                )
                messages.success(request, "Enlistment submitted. Waiting for adviser review.")
                return redirect("enrollment:student_subject_select", pk=enlistment.pk)
            except ValidationError as e:
                form.add_error(None, e.messages[0] if e.messages else "Unable to submit enlistment.")
    else:
        form = EnlistmentCreateForm()
    return render(request, "enrollment/enlistment_create.html", {"form": form})

@login_required
def enlistment_detail(request, pk):
    enlistment = get_object_or_404(Enlistment, pk=pk)
    # Students can see only theirs; adviser/finance can see all
    if request.user.role == User.Role.STUDENT and enlistment.student_id != request.user.id:
        raise PermissionDenied("Not your enlistment.")
    return render(request, "enrollment/enlistment_detail.html", {"enlistment": enlistment})

@login_required
@role_required("STUDENT")
def student_pay(request, pk):
    enlistment = get_object_or_404(Enlistment, pk=pk, student=request.user)
    payment = getattr(enlistment, "payment", None)
    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            try:
                student_mark_paid(request.user, enlistment, reference=form.cleaned_data.get("reference", ""))
                messages.success(request, "Payment recorded. Enrollment confirmed.")
                return redirect("enrollment:enlistment_detail", pk=enlistment.pk)
            except Exception as e:
                messages.error(request, str(e))
    else:
        form = PaymentForm()
    return render(request, "enrollment/student_pay.html", {"enlistment": enlistment, "form": form, "payment": payment})

@login_required
@role_required("STUDENT")
def student_subject_select(request, pk):
    enlistment = get_object_or_404(Enlistment, pk=pk, student=request.user)
    window = EnrollmentWindow.get_solo()
    if not window.is_open:
        return render(
            request,
            "enrollment/enrollment_closed.html",
            {"message": window.message or "Enrollment is currently closed."},
        )
    if enlistment.status not in [Enlistment.Status.SUBMITTED, Enlistment.Status.RETURNED]:
        messages.error(request, "Subject selection is only allowed after submission.")
        return redirect("enrollment:enlistment_detail", pk=enlistment.pk)

    selected = list(enlistment.next_subjects.values_list("subject_id", flat=True))
    if request.method == "POST":
        form = StudentSubjectSelectForm(request.POST)
        if form.is_valid():
            EnlistmentSubject.objects.filter(enlistment=enlistment).delete()
            for subject in form.cleaned_data["subjects"]:
                EnlistmentSubject.objects.create(enlistment=enlistment, subject=subject)
            messages.success(request, "Subjects saved.")
            return redirect("enrollment:enlistment_detail", pk=enlistment.pk)
    else:
        form = StudentSubjectSelectForm(initial={"subjects": list(selected)})

    subjects = Subject.objects.all().order_by("code")
    return render(
        request,
        "enrollment/student_subject_select.html",
        {"enlistment": enlistment, "form": form, "subjects": subjects, "selected_ids": set(selected)},
    )

@login_required
@role_required("STUDENT")
def student_profile_personal(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        user_form = PersonalDetailsUserForm(request.POST, instance=request.user)
        profile_form = PersonalDetailsProfileForm(request.POST, instance=profile)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, "Personal details updated.")
            return redirect("enrollment:student_profile_personal")
    else:
        user_form = PersonalDetailsUserForm(instance=request.user)
        profile_form = PersonalDetailsProfileForm(instance=profile)
    return render(
        request,
        "enrollment/student_profile_personal.html",
        {"profile": profile, "user_form": user_form, "profile_form": profile_form},
    )

@login_required
@role_required("STUDENT")
def student_profile_address(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = AddressDetailsForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Address details updated.")
            return redirect("enrollment:student_profile_address")
    else:
        form = AddressDetailsForm(instance=profile)
    return render(
        request,
        "enrollment/student_profile_address.html",
        {"profile": profile, "form": form},
    )

@login_required
@role_required("STUDENT")
def student_profile_course(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = CourseDetailsForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Course details updated.")
            return redirect("enrollment:student_profile_course")
    else:
        form = CourseDetailsForm(instance=profile)
    return render(
        request,
        "enrollment/student_profile_course.html",
        {"profile": profile, "form": form},
    )

@login_required
@role_required("STUDENT")
def student_profile_enlisted(request):
    enlistments = Enlistment.objects.filter(student=request.user)
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    return render(
        request,
        "enrollment/student_profile_enlisted.html",
        {"enlistments": enlistments, "profile": profile},
    )

@login_required
@role_required("STUDENT")
def student_profile_schedule(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    return render(
        request,
        "enrollment/student_profile_schedule.html",
        {"profile": profile},
    )

# ---------------------- ADVISER ----------------------
@login_required
@role_required("ADVISER")
def adviser_dashboard(request):
    pending_pre = Enlistment.objects.filter(status__in=[Enlistment.Status.SUBMITTED, Enlistment.Status.RETURNED])
    pending_final = Enlistment.objects.filter(status=Enlistment.Status.FINANCE_APPROVED)
    return render(
        request,
        "enrollment/adviser_dashboard.html",
        {"pending_pre": pending_pre, "pending_final": pending_final},
    )

@login_required
@role_required("ADVISER")
def adviser_preapprove_view(request, pk):
    enlistment = get_object_or_404(Enlistment, pk=pk)
    try:
        adviser_preapprove(request.user, enlistment)
        messages.success(request, "Pre-approved and forwarded to Admin/Finance.")
    except Exception as e:
        messages.error(request, str(e))
    return redirect("enrollment:enlistment_detail", pk=enlistment.pk)

@login_required
@role_required("ADVISER")
def adviser_return_view(request, pk):
    enlistment = get_object_or_404(Enlistment, pk=pk)
    if request.method == "POST":
        form = ReturnReasonForm(request.POST)
        if form.is_valid():
            try:
                adviser_return_for_revision(request.user, enlistment, form.cleaned_data["reason"])
                messages.success(request, "Returned to student for revision.")
                return redirect("enrollment:enlistment_detail", pk=enlistment.pk)
            except Exception as e:
                messages.error(request, str(e))
    else:
        form = ReturnReasonForm()
    return render(request, "enrollment/adviser_return.html", {"enlistment": enlistment, "form": form})

@login_required
@role_required("ADVISER")
def adviser_final_approve_view(request, pk):
    enlistment = get_object_or_404(Enlistment, pk=pk)
    if request.method == "POST":
        form = SubjectSelectForm(request.POST)
        if form.is_valid():
            try:
                adviser_final_approve_and_add_subjects(
                    request.user,
                    enlistment,
                    subject_ids=[s.id for s in form.cleaned_data["subjects"]],
                )
                messages.success(request, "Final approval complete. Student can proceed to payment.")
                return redirect("enrollment:enlistment_detail", pk=enlistment.pk)
            except Exception as e:
                messages.error(request, str(e))
    else:
        form = SubjectSelectForm()
    return render(request, "enrollment/adviser_final_approve.html", {"enlistment": enlistment, "form": form})

# ---------------------- FINANCE ----------------------
@login_required
@role_required("FINANCE")
def finance_dashboard(request):
    pending = Enlistment.objects.filter(status=Enlistment.Status.FINANCE_REVIEW)
    holds = Enlistment.objects.filter(status__in=[Enlistment.Status.FINANCE_HOLD_BALANCE, Enlistment.Status.FINANCE_HOLD_ACADEMIC])
    window = EnrollmentWindow.get_solo()
    return render(request, "enrollment/finance_dashboard.html", {"pending": pending, "holds": holds, "window": window})

@login_required
@role_required("FINANCE")
def finance_review_view(request, pk):
    enlistment = get_object_or_404(Enlistment, pk=pk)
    try:
        finance_review(request.user, enlistment, approve_if_ok=True)
        if enlistment.status == Enlistment.Status.FINANCE_APPROVED:
            messages.success(request, "Cleared. Adviser can now finalize and add subjects.")
        else:
            messages.warning(request, f"Held: {enlistment.hold_reason}")
    except Exception as e:
        messages.error(request, str(e))
    return redirect("enrollment:enlistment_detail", pk=enlistment.pk)

@login_required
@role_required("FINANCE")
def finance_toggle_enrollment(request):
    window = EnrollmentWindow.get_solo()
    if request.method == "POST":
        action = request.POST.get("action")
        message = request.POST.get("message", "").strip()
        if action == "close":
            window.is_open = False
            window.message = message or "Enrollment is currently closed."
            window.save(update_fields=["is_open", "message", "updated_at"])
            messages.success(request, "Enrollment closed.")
        elif action == "open":
            window.is_open = True
            window.message = ""
            window.save(update_fields=["is_open", "message", "updated_at"])
            messages.success(request, "Enrollment opened.")
    return redirect("enrollment:finance_dashboard")

@login_required
@role_required("FINANCE")
def finance_set_amount_view(request, pk):
    enlistment = get_object_or_404(Enlistment, pk=pk)
    if enlistment.status not in [
        Enlistment.Status.FINANCE_APPROVED,
        Enlistment.Status.APPROVED_FOR_PAYMENT,
        Enlistment.Status.ENROLLED,
    ]:
        messages.error(request, "Amount can be set only after finance approval.")
        return redirect("enrollment:enlistment_detail", pk=enlistment.pk)
    if request.method == "POST":
        form = FinanceAmountForm(request.POST)
        if form.is_valid():
            try:
                finance_set_amount(request.user, enlistment, form.cleaned_data["amount"])
                messages.success(request, "Amount updated.")
                return redirect("enrollment:enlistment_detail", pk=enlistment.pk)
            except Exception as e:
                messages.error(request, str(e))
    else:
        payment = getattr(enlistment, "payment", None)
        form = FinanceAmountForm(initial={"amount": payment.amount if payment else 0})
    return render(request, "enrollment/finance_set_amount.html", {"enlistment": enlistment, "form": form})

# ---------------------- HISTORY ----------------------
@login_required
@role_required("ADVISER", "FINANCE")
def history_log(request):
    logs = HistoryLog.objects.select_related("actor", "enlistment", "enlistment__student")

    action = request.GET.get("action") or ""
    actor = request.GET.get("actor") or ""
    student = request.GET.get("student") or ""

    if action:
        logs = logs.filter(action=action)
    if actor:
        logs = logs.filter(actor__username__icontains=actor)
    if student:
        logs = logs.filter(enlistment__student__student_number__icontains=student)

    logs = logs[:200]
    return render(
        request,
        "enrollment/history_log.html",
        {"logs": logs, "filter_action": action, "filter_actor": actor, "filter_student": student},
    )

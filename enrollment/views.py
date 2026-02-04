from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from accounts.models import User
from .models import Enlistment, HistoryLog
from .forms import EnlistmentCreateForm, ReturnReasonForm, SubjectSelectForm, PaymentForm, FinanceAmountForm
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
    enlistments = Enlistment.objects.filter(student=request.user)
    return render(request, "enrollment/student_dashboard.html", {"enlistments": enlistments})

@login_required
@role_required("STUDENT")
def student_enlistment_create(request):
    if request.method == "POST":
        form = EnlistmentCreateForm(request.POST)
        if form.is_valid():
            try:
                enlistment = student_submit_enlistment(
                    request.user,
                    category=form.cleaned_data["category"],
                    school_year=form.cleaned_data["school_year"].label,
                    semester=form.cleaned_data["semester"].name,
                    notes=form.cleaned_data.get("notes", ""),
                )
                messages.success(request, "Enlistment submitted. Waiting for adviser review.")
                return redirect("enrollment:enlistment_detail", pk=enlistment.pk)
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
    return render(request, "enrollment/finance_dashboard.html", {"pending": pending, "holds": holds})

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
    logs = HistoryLog.objects.select_related("actor", "enlistment", "enlistment__student")[:200]
    return render(request, "enrollment/history_log.html", {"logs": logs})

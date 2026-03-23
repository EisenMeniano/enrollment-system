from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from decimal import Decimal, ROUND_DOWN

from accounts.models import User, StudentProfile
from accounts.forms import PersonalDetailsUserForm, PersonalDetailsProfileForm, AddressDetailsForm, CourseDetailsForm, PhotoSignatureForm
from .models import (
    Enlistment,
    EnlistmentBlock,
    EnlistmentBlockSubject,
    Payment,
    HistoryLog,
    EnlistmentSubject,
    Subject,
    EnrollmentWindow,
    SchoolYear,
    AttendanceRecord,
    OverallResult,
    ExamPermit,
    ExamSchedule,
    DefermentRequest,
    CurriculumProgressSummary,
    CurriculumProgressCourse,
    StudentProfileMenuItem,
)
from .forms import (
    EnlistmentCreateForm,
    ReturnReasonForm,
    PaymentForm,
    FinanceAmountForm,
    FinanceBlockSetupForm,
    StudentBlockSelectForm,
)
from .services import (
    student_submit_enlistment,
    adviser_preapprove,
    adviser_return_for_revision,
    finance_review,
    adviser_final_approve_and_add_subjects,
    student_mark_paid,
    finance_set_amount,
    finance_record_payment,
)

def role_required(*roles):
    def decorator(view_func):
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated or request.user.role not in roles:
                raise PermissionDenied("You do not have access to this page.")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def _parse_block_schedule_lines(raw_lines):
    def _normalize(text):
        return "".join(ch for ch in (text or "").upper() if ch.isalnum())

    subjects = list(Subject.objects.all())
    subjects_by_code = {_normalize(subject.code): subject for subject in subjects}

    def _make_subject_from_text(subject_hint):
        base = _normalize(subject_hint)[:20] or "SUBJ"
        code = base
        counter = 2
        while Subject.objects.filter(code=code).exists():
            suffix = str(counter)
            code = f"{base[: max(1, 20 - len(suffix))]}{suffix}"
            counter += 1
        title = subject_hint.strip() or code
        subject = Subject.objects.create(code=code, title=title, units=3)
        subjects_by_code[_normalize(subject.code)] = subject
        subjects.append(subject)
        return subject

    def _resolve_subject(subject_hint):
        norm_hint = _normalize(subject_hint)
        if not norm_hint:
            return None
        if norm_hint in subjects_by_code:
            return subjects_by_code[norm_hint]
        for code_norm, subject in subjects_by_code.items():
            if code_norm.startswith(norm_hint):
                return subject
        for subject in subjects:
            if norm_hint in _normalize(subject.title):
                return subject
        # Fallback: allow entering title keywords instead of exact code.
        hint_words = [w for w in subject_hint.strip().split() if w]
        if not hint_words:
            return _make_subject_from_text(subject_hint)
        for subject in subjects:
            title_up = (subject.title or "").upper()
            if all(word.upper() in title_up for word in hint_words):
                return subject
        return _make_subject_from_text(subject_hint)

    parsed_items = []
    errors = []
    for line_no, raw_line in enumerate((raw_lines or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        # Accept flexible formats:
        # ENG101 | 7:30 - 9:00
        # ENG 101 - 7:30 - 9:00
        subject_hint = ""
        schedule = ""
        if "|" in line:
            subject_hint, schedule = [part.strip() for part in line.split("|", 1)]
        elif " - " in line:
            subject_hint, schedule = [part.strip() for part in line.split(" - ", 1)]
        else:
            tokens = line.split(None, 1)
            subject_hint = tokens[0].strip() if tokens else ""
            schedule = tokens[1].strip() if len(tokens) > 1 else ""

        if not subject_hint:
            errors.append(f"Line {line_no}: add a subject name/code.")
            continue
        if not schedule:
            schedule = "TBA"

        subject = _resolve_subject(subject_hint)
        if not subject:
            errors.append(f"Line {line_no}: could not resolve subject '{subject_hint}'.")
            continue
        parsed_items.append((subject, schedule))
    if not parsed_items and not errors:
        errors.append("Add at least one schedule line.")
    return parsed_items, errors


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
                messages.success(
                    request,
                    "Enrollment submitted. Waiting for adviser and finance review before subject enlistment.",
                )
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
    payment_kind = (request.POST.get("payment_kind") or request.GET.get("fee_kind") or "TUITION").upper()
    if payment_kind not in {"ENLISTMENT", "TUITION"}:
        payment_kind = "TUITION"
    prefill_reference = request.GET.get("reference", "")
    due_amount = Decimal("0.00")
    if payment:
        due_amount = payment.enlistment_amount if payment_kind == "ENLISTMENT" else payment.tuition_amount
    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            try:
                # Counter-payment flow: student marks payment intent, finance confirms later.
                amount_to_submit = due_amount
                student_mark_paid(
                    request.user,
                    enlistment,
                    amount=amount_to_submit,
                    reference=form.cleaned_data.get("reference", ""),
                    payment_kind=payment_kind,
                )
                messages.success(request, "Payment is pending finance approval.")
                return redirect("enrollment:enlistment_detail", pk=enlistment.pk)
            except Exception as e:
                messages.error(request, str(e))
    else:
        initial_amount = due_amount
        initial_reference = prefill_reference or (payment.reference if payment else "")
        form = PaymentForm(initial={"amount": initial_amount, "reference": initial_reference})
    # Amount is fixed to due amount for counter-payment flow.
    form.fields["amount"].widget.attrs["readonly"] = True
    form.fields["amount"].help_text = "Fixed due amount for cashier/counter verification."
    return render(
        request,
        "enrollment/student_pay.html",
        {
            "enlistment": enlistment,
            "form": form,
            "payment": payment,
            "payment_kind": payment_kind,
            "due_amount": due_amount,
        },
    )

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
    if enlistment.status != Enlistment.Status.APPROVED_FOR_PAYMENT:
        messages.error(
            request,
            "Apply for Enlistment opens only after adviser final approval.",
        )
        return redirect("enrollment:enlistment_detail", pk=enlistment.pk)
    payment = getattr(enlistment, "payment", None)
    if not payment or not payment.enlistment_paid:
        messages.error(
            request,
            "Pay and clear the enlistment fee first. Subject enlistment opens after finance approves it.",
        )
        return redirect("enrollment:enlistment_detail", pk=enlistment.pk)

    available_blocks = (
        EnlistmentBlock.objects.filter(enlistment=enlistment)
        .prefetch_related("subjects__subject")
        .order_by("name")
    )
    if not available_blocks.exists():
        messages.error(request, "Finance has not configured block schedules yet.")
        return redirect("enrollment:enlistment_detail", pk=enlistment.pk)

    if request.method == "POST":
        form = StudentBlockSelectForm(request.POST, block_queryset=available_blocks)
        if form.is_valid():
            selected_block = form.cleaned_data["block"]
            enlistment.selected_block = selected_block
            enlistment.save(update_fields=["selected_block", "updated_at"])

            # Keep next_subjects synchronized for existing pages/reports.
            EnlistmentSubject.objects.filter(enlistment=enlistment).delete()
            for block_subject in selected_block.subjects.select_related("subject"):
                EnlistmentSubject.objects.get_or_create(enlistment=enlistment, subject=block_subject.subject)

            payment, _ = Payment.objects.get_or_create(
                enlistment=enlistment,
                defaults={
                    "enlistment_amount": 0,
                    "tuition_amount": 0,
                    "amount": 0,
                    "status": Payment.Status.PENDING,
                },
            )
            payment.tuition_amount = selected_block.tuition_amount
            payment.amount = selected_block.tuition_amount
            payment.save(update_fields=["tuition_amount", "amount"])

            messages.success(
                request,
                f"Block '{selected_block.name}' selected. Final tuition fee is {selected_block.tuition_amount}.",
            )
            return redirect("enrollment:enlistment_detail", pk=enlistment.pk)
    else:
        form = StudentBlockSelectForm(
            initial={"block": enlistment.selected_block_id},
            block_queryset=available_blocks,
        )
    return render(
        request,
        "enrollment/student_subject_select.html",
        {
            "enlistment": enlistment,
            "form": form,
            "blocks": available_blocks,
            "selected_block": enlistment.selected_block,
        },
    )

@login_required
@role_required("STUDENT")
def student_profile_personal(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    latest_enlistment = Enlistment.objects.filter(student=request.user).first()
    menu_items = StudentProfileMenuItem.get_menu()
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
        {
            "profile": profile,
            "user_form": user_form,
            "profile_form": profile_form,
            "latest_enlistment": latest_enlistment,
            "menu_items": menu_items,
        },
    )

@login_required
@role_required("STUDENT")
def student_profile_address(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    latest_enlistment = Enlistment.objects.filter(student=request.user).first()
    menu_items = StudentProfileMenuItem.get_menu()
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
        {"profile": profile, "form": form, "latest_enlistment": latest_enlistment, "menu_items": menu_items},
    )

@login_required
@role_required("STUDENT")
def student_profile_course(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    latest_enlistment = Enlistment.objects.filter(student=request.user).first()
    menu_items = StudentProfileMenuItem.get_menu()
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
        {"profile": profile, "form": form, "latest_enlistment": latest_enlistment, "menu_items": menu_items},
    )

@login_required
@role_required("STUDENT")
def student_profile_enlisted(request):
    enlistments = Enlistment.objects.filter(student=request.user)
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    latest_enlistment = enlistments.first()
    menu_items = StudentProfileMenuItem.get_menu()
    sessions = SchoolYear.objects.order_by("-label")
    selected_session_id = request.GET.get("session")
    if selected_session_id:
        try:
            session = SchoolYear.objects.get(id=selected_session_id)
            enlistments = enlistments.filter(school_year=session.label)
        except SchoolYear.DoesNotExist:
            pass
    return render(
        request,
        "enrollment/student_profile_enlisted.html",
        {
            "enlistments": enlistments,
            "profile": profile,
            "latest_enlistment": latest_enlistment,
            "menu_items": menu_items,
            "sessions": sessions,
            "selected_session_id": selected_session_id or "",
        },
    )

@login_required
@role_required("STUDENT")
def student_profile_schedule(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    latest_enlistment = Enlistment.objects.filter(student=request.user).first()
    sessions = SchoolYear.objects.order_by("-label")
    menu_items = StudentProfileMenuItem.get_menu()
    return render(
        request,
        "enrollment/student_profile_schedule.html",
        {"profile": profile, "sessions": sessions, "latest_enlistment": latest_enlistment, "menu_items": menu_items},
    )

def _student_profile_placeholder(request, active, title):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    latest_enlistment = Enlistment.objects.filter(student=request.user).first()
    menu_items = StudentProfileMenuItem.get_menu()
    return render(
        request,
        "enrollment/student_profile_placeholder.html",
        {
            "profile": profile,
            "active": active,
            "title": title,
            "latest_enlistment": latest_enlistment,
            "menu_items": menu_items,
        },
    )


def _build_payment_breakdown(enlistment, credit=None, include_downpayment=True):
    zero = Decimal("0.00")
    total = zero
    credit = credit if credit is not None else zero
    if enlistment and getattr(enlistment, "payment", None):
        total = enlistment.payment.tuition_amount or zero
    if credit < zero:
        credit = zero
    credit = credit.quantize(Decimal("0.01"))

    if include_downpayment:
        # Down payment is separate from tuition and handled on Down Payment page.
        down_payment = enlistment.payment.enlistment_amount if enlistment and getattr(enlistment, "payment", None) else zero
        remaining_after_downpayment = total
    else:
        down_payment = zero
        remaining_after_downpayment = total

    base_term = (remaining_after_downpayment / Decimal("3")).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    prelim = base_term
    midterm = base_term
    final = (remaining_after_downpayment - prelim - midterm).quantize(Decimal("0.01"))

    remaining_credit = max(credit - down_payment, zero)

    return {
        "total": total,
        "down_payment": down_payment,
        "remaining_after_downpayment": remaining_after_downpayment,
        "prelim": prelim,
        "midterm": midterm,
        "final": final,
        "remaining_credit": remaining_credit,
    }

@login_required
@role_required("STUDENT")
def student_profile_photo(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    latest_enlistment = Enlistment.objects.filter(student=request.user).first()
    menu_items = StudentProfileMenuItem.get_menu()
    if request.method == "POST":
        form = PhotoSignatureForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Photo and signature updated.")
            return redirect("enrollment:student_profile_photo")
    else:
        form = PhotoSignatureForm(instance=profile)
    return render(
        request,
        "enrollment/student_profile_photo.html",
        {"profile": profile, "form": form, "latest_enlistment": latest_enlistment, "menu_items": menu_items},
    )

@login_required
@role_required("STUDENT")
def student_profile_grade(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    latest_enlistment = Enlistment.objects.filter(student=request.user).first()
    sessions = SchoolYear.objects.order_by("-label")
    menu_items = StudentProfileMenuItem.get_menu()
    return render( 
        request,
        "enrollment/student_profile_grade.html",
        {"profile": profile, "sessions": sessions, "latest_enlistment": latest_enlistment, "menu_items": menu_items},
    )

@login_required
@role_required("STUDENT")
def student_profile_attendance(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    latest_enlistment = Enlistment.objects.filter(student=request.user).first()
    sessions = SchoolYear.objects.order_by("-label")
    menu_items = StudentProfileMenuItem.get_menu()
    selected_session_id = request.GET.get("session")
    if selected_session_id:
        records = AttendanceRecord.objects.filter(student=request.user, session_id=selected_session_id)
    else:
        records = AttendanceRecord.objects.filter(student=request.user)
    return render(
        request,
        "enrollment/student_profile_attendance.html",
        {
            "profile": profile,
            "sessions": sessions,
            "latest_enlistment": latest_enlistment,
            "attendance_records": records,
            "selected_session_id": selected_session_id or "",
            "menu_items": menu_items,
        },
    )

@login_required
@role_required("STUDENT")
def student_profile_overall(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    latest_enlistment = Enlistment.objects.filter(student=request.user).first()
    sessions = SchoolYear.objects.order_by("-label")
    menu_items = StudentProfileMenuItem.get_menu()
    selected_session_id = request.GET.get("session")
    results = OverallResult.objects.filter(student=request.user)
    if selected_session_id:
        results = results.filter(session_id=selected_session_id)
    selected_result = results.first()
    items = selected_result.items.all() if selected_result else []
    return render(
        request,
        "enrollment/student_profile_overall.html",
        {
            "profile": profile,
            "sessions": sessions,
            "latest_enlistment": latest_enlistment,
            "overall_results": results,
            "overall_items": items,
            "selected_session_id": selected_session_id or "",
            "menu_items": menu_items,
        },
    )

@login_required
@role_required("STUDENT")
def student_profile_permit(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    latest_enlistment = Enlistment.objects.filter(student=request.user).first()
    sessions = SchoolYear.objects.order_by("-label")
    menu_items = StudentProfileMenuItem.get_menu()
    selected_session_id = request.GET.get("session")
    permits = ExamPermit.objects.filter(student=request.user)
    if selected_session_id:
        permits = permits.filter(session_id=selected_session_id)
    permit = permits.first()
    return render(
        request,
        "enrollment/student_profile_permit.html",
        {
            "profile": profile,
            "sessions": sessions,
            "latest_enlistment": latest_enlistment,
            "permit": permit,
            "selected_session_id": selected_session_id or "",
            "menu_items": menu_items,
        },
    )

@login_required
@role_required("STUDENT")
def student_profile_document(request):
    return _student_profile_placeholder(request, "document", "Document")

@login_required
@role_required("STUDENT")
def student_profile_exam_schedule(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    latest_enlistment = Enlistment.objects.filter(student=request.user).first()
    sessions = SchoolYear.objects.order_by("-label")
    menu_items = StudentProfileMenuItem.get_menu()
    selected_session_id = request.GET.get("session")
    schedules = ExamSchedule.objects.filter(student=request.user)
    if selected_session_id:
        schedules = schedules.filter(session_id=selected_session_id)
    return render(
        request,
        "enrollment/student_profile_exam_schedule.html",
        {
            "profile": profile,
            "sessions": sessions,
            "latest_enlistment": latest_enlistment,
            "schedules": schedules,
            "selected_session_id": selected_session_id or "",
            "menu_items": menu_items,
        },
    )

@login_required
@role_required("STUDENT")
def student_profile_deferment(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    latest_enlistment = Enlistment.objects.filter(student=request.user).first()
    sessions = SchoolYear.objects.order_by("-label")
    menu_items = StudentProfileMenuItem.get_menu()
    if request.method == "POST":
        session_id = request.POST.get("session") or None
        DefermentRequest.objects.create(
            student=request.user,
            session_id=session_id if session_id else None,
            num_semesters=int(request.POST.get("num_semesters") or 1),
            deferment_type=request.POST.get("deferment_type") or "",
            reason=request.POST.get("reason") or "",
        )
        messages.success(request, "Deferment request submitted.")
        return redirect("enrollment:student_profile_deferment")
    requests = DefermentRequest.objects.filter(student=request.user)
    return render(
        request,
        "enrollment/student_profile_deferment.html",
        {
            "profile": profile,
            "sessions": sessions,
            "latest_enlistment": latest_enlistment,
            "requests": requests,
            "menu_items": menu_items,
        },
    )

@login_required
@role_required("STUDENT")
def student_profile_curriculum(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    latest_enlistment = Enlistment.objects.filter(student=request.user).first()
    sessions = SchoolYear.objects.order_by("-label")
    menu_items = StudentProfileMenuItem.get_menu()
    selected_session_id = request.GET.get("session")
    summary = CurriculumProgressSummary.objects.filter(student=request.user)
    if selected_session_id:
        summary = summary.filter(session_id=selected_session_id)
    summary = summary.first()
    courses = CurriculumProgressCourse.objects.filter(student=request.user)
    if selected_session_id:
        courses = courses.filter(session_id=selected_session_id)
    return render(
        request,
        "enrollment/student_profile_curriculum.html",
        {
            "profile": profile,
            "sessions": sessions,
            "latest_enlistment": latest_enlistment,
            "summary": summary,
            "courses": courses,
            "selected_session_id": selected_session_id or "",
            "menu_items": menu_items,
        },
    )


@login_required
@role_required("STUDENT")
def student_downpayment(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    latest_enlistment = Enlistment.objects.filter(student=request.user).first()
    menu_items = StudentProfileMenuItem.get_menu()
    finance_account = getattr(request.user, "finance_account", None)
    carry_over_credit = Decimal("0.00")
    if finance_account and finance_account.balance < 0:
        carry_over_credit = abs(finance_account.balance)
    payment_breakdown = _build_payment_breakdown(
        latest_enlistment,
        credit=carry_over_credit,
        include_downpayment=True,
    )
    downpayment_open_statuses = {
        Enlistment.Status.SUBMITTED,
        Enlistment.Status.RETURNED,
        Enlistment.Status.FINANCE_REVIEW,
        Enlistment.Status.FINANCE_APPROVED,
    }
    downpayment_enabled = False
    downpayment_message = ""
    if not latest_enlistment:
        downpayment_message = "No enlistment found yet. Submit enlistment first."
    elif latest_enlistment.status not in downpayment_open_statuses:
        downpayment_message = "Down payment is for enlistment only. Continue in My Payment for enrollment tuition."
    elif latest_enlistment.payment.enlistment_paid if getattr(latest_enlistment, "payment", None) else False:
        downpayment_message = "Enlistment fee is already paid."
    elif payment_breakdown["down_payment"] <= 0:
        downpayment_message = "No down payment amount is currently set for this enlistment."
    else:
        downpayment_enabled = True

    return render(
        request,
        "enrollment/student_downpayment.html",
        {
            "profile": profile,
            "latest_enlistment": latest_enlistment,
            "menu_items": menu_items,
            "payment_breakdown": payment_breakdown,
            "downpayment_enabled": downpayment_enabled,
            "downpayment_message": downpayment_message,
        },
    )


@login_required
@role_required("STUDENT")
def student_enlistment_page(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    enlistments = Enlistment.objects.filter(student=request.user).select_related(
        "category",
        "program",
        "selected_block",
        "payment",
    )
    latest_enlistment = enlistments.first()
    menu_items = StudentProfileMenuItem.get_menu()
    apply_enlistment = (
        enlistments.filter(
            status=Enlistment.Status.APPROVED_FOR_PAYMENT,
            payment__enlistment_paid=True,
            block_options__subjects__isnull=False,
        )
        .distinct()
        .first()
    )
    apply_enlistment_reason = ""
    if not apply_enlistment:
        if not latest_enlistment:
            apply_enlistment_reason = "Apply for Enlistment is locked. Click Enrollment first."
        elif latest_enlistment.status in {
            Enlistment.Status.SUBMITTED,
            Enlistment.Status.RETURNED,
            Enlistment.Status.FINANCE_REVIEW,
            Enlistment.Status.FINANCE_HOLD_BALANCE,
            Enlistment.Status.FINANCE_HOLD_ACADEMIC,
            Enlistment.Status.FINANCE_APPROVED,
        }:
            apply_enlistment_reason = (
                "Apply for Enlistment is locked while your enrollment is under adviser/finance review."
            )
        elif latest_enlistment.status == Enlistment.Status.APPROVED_FOR_PAYMENT:
            latest_payment = getattr(latest_enlistment, "payment", None)
            if not latest_payment or not latest_payment.enlistment_paid:
                apply_enlistment_reason = (
                    "Apply for Enlistment is locked. Pay and clear enlistment fee first."
                )
            else:
                apply_enlistment_reason = "Waiting for finance to set blocks/schedules before you can apply."
        elif latest_enlistment.status == Enlistment.Status.ENROLLED:
            apply_enlistment_reason = "Your latest enrollment is already confirmed."
        else:
            apply_enlistment_reason = "Apply for Enlistment is currently unavailable."
    return render(
        request,
        "enrollment/student_enlistment_page.html",
        {
            "profile": profile,
            "latest_enlistment": latest_enlistment,
            "menu_items": menu_items,
            "enlistments": enlistments,
            "apply_enlistment": apply_enlistment,
            "apply_enlistment_reason": apply_enlistment_reason,
        },
    )


@login_required
@role_required("STUDENT")
def student_my_payment(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    latest_enlistment = Enlistment.objects.filter(student=request.user).first()
    menu_items = StudentProfileMenuItem.get_menu()
    finance_account = getattr(request.user, "finance_account", None)
    carry_over_credit = Decimal("0.00")
    if finance_account and finance_account.balance < 0:
        carry_over_credit = abs(finance_account.balance)
    payment_breakdown = _build_payment_breakdown(
        latest_enlistment,
        credit=carry_over_credit,
        include_downpayment=False,
    )
    my_payment_open_statuses = {
        Enlistment.Status.APPROVED_FOR_PAYMENT,
        Enlistment.Status.ENROLLED,
    }
    my_payment_enabled = False
    my_payment_message = ""
    if not latest_enlistment:
        my_payment_message = "No enlistment found yet."
    elif latest_enlistment.status not in my_payment_open_statuses:
        my_payment_message = "My Payment opens only after adviser final approval and finance tuition setup."
    elif not latest_enlistment.selected_block_id:
        my_payment_message = "Choose your block/schedule first in Apply for Enlistment to generate final tuition."
    elif not getattr(latest_enlistment, "payment", None) or not latest_enlistment.payment.enlistment_paid:
        my_payment_message = "Pay and clear enlistment fee first before tuition payment."
    elif payment_breakdown["total"] <= 0:
        my_payment_message = "Final tuition is not ready yet. Please reselect your block/schedule."
    elif payment_breakdown["remaining_after_downpayment"] <= 0:
        my_payment_message = "No remaining enrollment balance to pay."
    else:
        my_payment_enabled = True

    return render(
        request,
        "enrollment/student_my_payment.html",
        {
            "profile": profile,
            "latest_enlistment": latest_enlistment,
            "menu_items": menu_items,
            "payment_breakdown": payment_breakdown,
            "my_payment_enabled": my_payment_enabled,
            "my_payment_message": my_payment_message,
        },
    )


@login_required
@role_required("STUDENT")
def student_inc_completion(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    latest_enlistment = Enlistment.objects.filter(student=request.user).first()
    menu_items = StudentProfileMenuItem.get_menu()
    return render(
        request,
        "enrollment/student_inc_completion.html",
        {"profile": profile, "latest_enlistment": latest_enlistment, "menu_items": menu_items},
    )

# ---------------------- ADVISER ----------------------
@login_required
@role_required("ADVISER")
def adviser_dashboard(request):
    pending_pre = Enlistment.objects.filter(status__in=[Enlistment.Status.SUBMITTED, Enlistment.Status.RETURNED])
    pending_final = (
        Enlistment.objects.filter(status=Enlistment.Status.FINANCE_APPROVED)
        .select_related("payment", "category", "program")
        .prefetch_related("block_options__subjects")
    )
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
    available_blocks = (
        EnlistmentBlock.objects.filter(enlistment=enlistment)
        .prefetch_related("subjects__subject")
        .order_by("name")
    )
    if not available_blocks.exists():
        messages.error(request, "Finance must configure at least one block/schedule before final adviser approval.")
        return redirect("enrollment:enlistment_detail", pk=enlistment.pk)
    payment = getattr(enlistment, "payment", None)
    if not payment or payment.enlistment_amount <= 0:
        messages.error(request, "Finance must set enlistment fee first before adviser final approval.")
        return redirect("enrollment:enlistment_detail", pk=enlistment.pk)

    if request.method == "POST":
        try:
            adviser_final_approve_and_add_subjects(request.user, enlistment)
            messages.success(
                request,
                "Enlistment approved. Student can now pay enlistment fee. Subject/block choice opens after finance approves that payment.",
            )
            return redirect("enrollment:enlistment_detail", pk=enlistment.pk)
        except Exception as e:
            messages.error(request, str(e))
    return render(
        request,
        "enrollment/adviser_final_approve.html",
        {"enlistment": enlistment, "available_blocks": available_blocks},
    )

# ---------------------- FINANCE ----------------------
@login_required
@role_required("FINANCE")
def finance_dashboard(request):
    pending = Enlistment.objects.filter(status=Enlistment.Status.FINANCE_REVIEW)
    holds = Enlistment.objects.filter(
        status__in=[Enlistment.Status.FINANCE_HOLD_BALANCE, Enlistment.Status.FINANCE_HOLD_ACADEMIC]
    )
    setup_required = (
        Enlistment.objects.filter(status=Enlistment.Status.FINANCE_APPROVED)
        .select_related("category", "program")
        .prefetch_related("block_options")
    )
    approved_for_payment = Enlistment.objects.filter(status=Enlistment.Status.APPROVED_FOR_PAYMENT).select_related(
        "selected_block"
    )
    pending_payment_approval = approved_for_payment.filter(payment__status=Payment.Status.SUBMITTED)
    window = EnrollmentWindow.get_solo()
    return render(
        request,
        "enrollment/finance_dashboard.html",
        {
            "pending": pending,
            "holds": holds,
            "setup_required": setup_required,
            "approved_for_payment": approved_for_payment,
            "pending_payment_approval": pending_payment_approval,
            "window": window,
        },
    )

@login_required
@role_required("FINANCE")
def finance_review_view(request, pk):
    enlistment = get_object_or_404(Enlistment, pk=pk)
    try:
        finance_review(request.user, enlistment, approve_if_ok=True)
        if enlistment.status == Enlistment.Status.FINANCE_APPROVED:
            messages.success(request, "Cleared. Finance should now set blocks/schedules and tuition per block.")
        else:
            messages.warning(request, f"Held: {enlistment.hold_reason}")
    except Exception as e:
        messages.error(request, str(e))
    return redirect("enrollment:enlistment_detail", pk=enlistment.pk)


@login_required
@role_required("FINANCE")
def finance_subject_setup_view(request, pk):
    enlistment = get_object_or_404(Enlistment, pk=pk)
    if enlistment.status not in [Enlistment.Status.FINANCE_APPROVED, Enlistment.Status.APPROVED_FOR_PAYMENT]:
        messages.error(request, "Blocks and schedules can be managed only after finance clearance.")
        return redirect("enrollment:enlistment_detail", pk=enlistment.pk)

    payment = getattr(enlistment, "payment", None)
    if request.method == "POST":
        form = FinanceBlockSetupForm(request.POST)
        if form.is_valid():
            parsed_items, parse_errors = _parse_block_schedule_lines(form.cleaned_data["schedule_lines"])
            if parse_errors:
                form.add_error("schedule_lines", " ".join(parse_errors))
            else:
                block_name = form.cleaned_data["block_name"].strip()
                tuition_amount = form.cleaned_data["tuition_amount"]
                enlistment_amount = form.cleaned_data["enlistment_amount"]

                block, _ = EnlistmentBlock.objects.get_or_create(
                    enlistment=enlistment,
                    name=block_name,
                    defaults={"created_by": request.user},
                )
                block.tuition_amount = tuition_amount
                block.created_by = request.user
                block.save(update_fields=["tuition_amount", "created_by", "updated_at"])

                EnlistmentBlockSubject.objects.filter(block=block).delete()
                for subject, schedule in parsed_items:
                    EnlistmentBlockSubject.objects.create(block=block, subject=subject, schedule=schedule)

                payment, _ = Payment.objects.get_or_create(
                    enlistment=enlistment,
                    defaults={
                        "enlistment_amount": 0,
                        "tuition_amount": 0,
                        "amount": 0,
                        "status": Payment.Status.PENDING,
                    },
                )
                updates = []
                payment.enlistment_amount = enlistment_amount
                updates.append("enlistment_amount")
                if enlistment.selected_block_id == block.id:
                    payment.tuition_amount = block.tuition_amount
                    payment.amount = block.tuition_amount
                    updates.extend(["tuition_amount", "amount"])
                if updates:
                    payment.save(update_fields=list(dict.fromkeys(updates)))

                messages.success(
                    request,
                    (
                        f"Saved block '{block.name}' with {len(parsed_items)} subject schedule(s). "
                        "Next step: adviser should click Approve Enlistment."
                    ),
                )
                return redirect("enrollment:finance_subject_setup", pk=enlistment.pk)
    else:
        form = FinanceBlockSetupForm(
            initial={
                "enlistment_amount": payment.enlistment_amount if payment else 0,
            }
        )

    existing_blocks = (
        EnlistmentBlock.objects.filter(enlistment=enlistment)
        .prefetch_related("subjects__subject")
        .order_by("name")
    )
    return render(
        request,
        "enrollment/finance_subject_setup.html",
        {
            "enlistment": enlistment,
            "form": form,
            "existing_blocks": existing_blocks,
            "payment": payment,
        },
    )

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
                finance_set_amount(
                    request.user,
                    enlistment,
                    enlistment_amount=form.cleaned_data["enlistment_amount"],
                    tuition_amount=form.cleaned_data["tuition_amount"],
                )
                messages.success(request, "Amount updated.")
                return redirect("enrollment:enlistment_detail", pk=enlistment.pk)
            except Exception as e:
                messages.error(request, str(e))
    else:
        payment = getattr(enlistment, "payment", None)
        form = FinanceAmountForm(
            initial={
                "enlistment_amount": payment.enlistment_amount if payment else 0,
                "tuition_amount": payment.tuition_amount if payment else 0,
            }
        )
    return render(request, "enrollment/finance_set_amount.html", {"enlistment": enlistment, "form": form})

@login_required
@role_required("FINANCE")
def finance_record_payment_view(request, pk):
    enlistment = get_object_or_404(Enlistment, pk=pk)
    if enlistment.status != Enlistment.Status.APPROVED_FOR_PAYMENT:
        messages.error(request, "Payment can be entered only for enlistments approved for payment.")
        return redirect("enrollment:enlistment_detail", pk=enlistment.pk)

    payment = getattr(enlistment, "payment", None)
    if not payment:
        messages.error(request, "No payment setup found for this enlistment.")
        return redirect("enrollment:enlistment_detail", pk=enlistment.pk)
    if payment.status != Payment.Status.SUBMITTED:
        messages.error(request, "Waiting for student payment submission before finance approval.")
        return redirect("enrollment:finance_dashboard")

    remaining_enlistment_due = max((payment.enlistment_amount or 0) - (payment.enlistment_paid_amount or 0), 0)
    remaining_tuition_due = max((payment.tuition_amount or 0) - (payment.tuition_paid_amount or 0), 0)

    # Enforce flow: clear enlistment fee first, then tuition.
    if not payment.enlistment_paid:
        payment_kind = "ENLISTMENT"
        due_amount = remaining_enlistment_due
    else:
        payment_kind = "TUITION"
        due_amount = remaining_tuition_due

    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            try:
                _, fully_paid, overpayment, payment_kind = finance_record_payment(
                    request.user,
                    enlistment,
                    amount=form.cleaned_data["amount"],
                    reference=form.cleaned_data.get("reference", ""),
                    payment_kind=payment_kind,
                )
                if payment_kind == "ENLISTMENT" and fully_paid:
                    messages.success(request, "Enlistment fee fully paid. Tuition payment is now enabled.")
                elif fully_paid:
                    messages.success(request, "Tuition payment approved by finance. Enrollment confirmed.")
                else:
                    messages.success(
                        request,
                        "Payment approved by finance.",
                    )
                if overpayment > 0:
                    messages.info(request, f"Overpayment credit posted: {overpayment}.")
                return redirect("enrollment:finance_dashboard")
            except Exception as e:
                messages.error(request, str(e))
    else:
        initial_amount = payment.submitted_amount if payment.submitted_amount > 0 else due_amount
        form = PaymentForm(initial={"amount": initial_amount, "reference": payment.reference})
    return render(
        request,
        "enrollment/finance_record_payment.html",
        {
            "enlistment": enlistment,
            "form": form,
            "payment": payment,
            "payment_kind": payment_kind,
            "due_amount": due_amount,
        },
    )

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

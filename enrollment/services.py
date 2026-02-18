from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from decimal import Decimal
import re
from .models import Enlistment, Payment, EnlistmentSubject, Subject, HistoryLog, StudentFinanceAccount

def log_history(actor, enlistment, action, message=""):
    HistoryLog.objects.create(
        actor=actor,
        enlistment=enlistment,
        action=action,
        message=message or "",
    )

def require_role(user, roles):
    if not user.is_authenticated or user.role not in roles:
        raise PermissionDenied("You do not have access to this action.")


def _resolve_amount_due(enlistment, payment):
    zero = Decimal("0.00")
    amount_due = payment.amount or zero
    amount_set_log = (
        HistoryLog.objects.filter(enlistment=enlistment, action=HistoryLog.Action.AMOUNT_SET)
        .order_by("-created_at")
        .values_list("message", flat=True)
        .first()
    )
    if amount_set_log:
        match = re.search(r"Set amount to\s+([0-9]+(?:\.[0-9]+)?)", amount_set_log)
        if match:
            try:
                parsed = Decimal(match.group(1))
                if parsed > zero:
                    amount_due = parsed
            except Exception:
                pass
    return amount_due

def can_finance_approve(enlistment):
    # Rule 1: must have finance account and balance must be 0
    acct = getattr(enlistment.student, "finance_account", None)
    balance = acct.balance if acct else 0
    if balance and balance > 0:
        return False, "Unpaid balance. Please settle your account first."

    # Rule 2 (MVP): must have no failed subjects in previous term records
    failed = enlistment.student.previous_subjects.filter(passed=False).exists()
    if failed:
        return False, "Academic issue: previous term contains failed subject(s). Please consult your adviser."

    return True, ""

@transaction.atomic
def student_submit_enlistment(student, school_year, semester, category, program, notes=""):
    existing = Enlistment.objects.filter(
        student=student,
        school_year=school_year,
        semester=semester,
    ).exclude(status=Enlistment.Status.REJECTED)
    if existing.exists():
        raise ValidationError(
            "You already submitted an enlistment for this term. You may apply again only if it was rejected."
        )
    enlistment = Enlistment.objects.create(
        student=student,
        category=category,
        program=program,
        school_year=school_year,
        semester=semester,
        status=Enlistment.Status.SUBMITTED,
        notes=notes,
    )
    log_history(
        actor=student,
        enlistment=enlistment,
        action=HistoryLog.Action.SUBMITTED,
        message=f"Submitted enlistment for {school_year} {semester}.",
    )
    return enlistment

@transaction.atomic
def adviser_preapprove(user, enlistment):
    require_role(user, ["ADVISER"])
    if enlistment.status not in [Enlistment.Status.SUBMITTED, Enlistment.Status.RETURNED]:
        raise ValidationError("Enlistment is not waiting for adviser pre-approval.")
    enlistment.status = Enlistment.Status.FINANCE_REVIEW
    enlistment.hold_reason = ""
    enlistment.adviser_preapproved_by = user
    enlistment.save(update_fields=["status", "hold_reason", "adviser_preapproved_by", "updated_at"])
    log_history(
        actor=user,
        enlistment=enlistment,
        action=HistoryLog.Action.PREAPPROVED,
        message="Pre-approved and forwarded to Admin/Finance.",
    )
    return enlistment

@transaction.atomic
def adviser_return_for_revision(user, enlistment, reason):
    require_role(user, ["ADVISER"])
    if enlistment.status not in [Enlistment.Status.SUBMITTED, Enlistment.Status.FINANCE_APPROVED]:
        raise ValidationError("Enlistment is not in a state that can be returned.")
    enlistment.status = Enlistment.Status.RETURNED
    enlistment.hold_reason = reason
    enlistment.save(update_fields=["status", "hold_reason", "updated_at"])
    log_history(
        actor=user,
        enlistment=enlistment,
        action=HistoryLog.Action.RETURNED,
        message=reason,
    )
    return enlistment

@transaction.atomic
def finance_review(user, enlistment, approve_if_ok=True):
    require_role(user, ["FINANCE"])
    if enlistment.status != Enlistment.Status.FINANCE_REVIEW:
        raise ValidationError("Enlistment is not waiting for finance review.")

    ok, reason = can_finance_approve(enlistment)
    enlistment.finance_checked_by = user

    if ok and approve_if_ok:
        enlistment.status = Enlistment.Status.FINANCE_APPROVED
        enlistment.hold_reason = ""
    else:
        if "balance" in reason.lower():
            enlistment.status = Enlistment.Status.FINANCE_HOLD_BALANCE
        else:
            enlistment.status = Enlistment.Status.FINANCE_HOLD_ACADEMIC
        enlistment.hold_reason = reason

    enlistment.save(update_fields=["status", "hold_reason", "finance_checked_by", "updated_at"])
    if enlistment.status == Enlistment.Status.FINANCE_APPROVED:
        log_history(
            actor=user,
            enlistment=enlistment,
            action=HistoryLog.Action.FINANCE_REVIEWED,
            message="Cleared by Admin/Finance.",
        )
    else:
        log_history(
            actor=user,
            enlistment=enlistment,
            action=HistoryLog.Action.FINANCE_HELD,
            message=enlistment.hold_reason,
        )
    return enlistment

@transaction.atomic
def adviser_final_approve_and_add_subjects(user, enlistment, subject_ids):
    require_role(user, ["ADVISER"])
    if enlistment.status != Enlistment.Status.FINANCE_APPROVED:
        raise ValidationError("Enlistment must be cleared by finance before final approval.")
    if not subject_ids:
        raise ValidationError("Please add at least one subject for the next semester.")

    # Replace subjects
    EnlistmentSubject.objects.filter(enlistment=enlistment).delete()
    subjects = Subject.objects.filter(id__in=subject_ids)
    for s in subjects:
        EnlistmentSubject.objects.create(enlistment=enlistment, subject=s)

    enlistment.status = Enlistment.Status.APPROVED_FOR_PAYMENT
    enlistment.adviser_final_approved_by = user
    enlistment.hold_reason = ""
    enlistment.save(update_fields=["status", "adviser_final_approved_by", "hold_reason", "updated_at"])
    log_history(
        actor=user,
        enlistment=enlistment,
        action=HistoryLog.Action.FINAL_APPROVED,
        message="Final approval complete. Subjects added.",
    )

    # Initialize payment only when missing. Do not overwrite an amount already set by finance.
    payment, created = Payment.objects.get_or_create(
        enlistment=enlistment,
        defaults={
            "enlistment_amount": 0,
            "tuition_amount": 0,
            "amount": 0,
            "status": Payment.Status.PENDING,
        },
    )
    if not created:
        payment.status = Payment.Status.PENDING
        payment.save(update_fields=["status"])
    return enlistment

@transaction.atomic
def student_mark_paid(student, enlistment, amount, reference="", payment_kind="TUITION"):
    if enlistment.student_id != student.id:
        raise PermissionDenied("Not your enlistment.")
    if enlistment.status != Enlistment.Status.APPROVED_FOR_PAYMENT:
        raise ValidationError("Enlistment is not approved for payment.")

    payment, _ = Payment.objects.get_or_create(
        enlistment=enlistment,
        defaults={
            "enlistment_amount": 0,
            "tuition_amount": 0,
            "amount": 0,
        },
    )
    if amount <= 0:
        raise ValidationError("Payment amount must be greater than 0.")
    payment_kind = (payment_kind or "TUITION").upper()
    if payment_kind == "ENLISTMENT":
        expected_due = payment.enlistment_amount
        if expected_due <= 0:
            raise ValidationError("Enlistment fee is not set by finance yet.")
    else:
        if not payment.enlistment_paid:
            raise ValidationError("You can pay tuition only after enlistment fee is fully paid.")
        expected_due = payment.tuition_amount
        if expected_due <= 0:
            raise ValidationError("Tuition fee is not set by finance yet.")
        payment_kind = "TUITION"

    if amount > expected_due:
        raise ValidationError(f"Amount exceeds {payment_kind.lower()} fee due ({expected_due}).")

    payment.submitted_amount = amount
    payment.status = Payment.Status.SUBMITTED
    payment.reference = reference
    payment.amount = payment.tuition_amount
    payment.save(update_fields=["amount", "submitted_amount", "status", "reference"])

    log_history(
        actor=student,
        enlistment=enlistment,
        action=HistoryLog.Action.PAYMENT_RECORDED,
        message=(
            f"{payment_kind.title()} payment submitted for finance approval: {amount}. Ref: {reference}"
            if reference
            else f"{payment_kind.title()} payment submitted for finance approval: {amount}."
        ),
    )
    return enlistment

@transaction.atomic
def finance_set_amount(user, enlistment, enlistment_amount, tuition_amount):
    require_role(user, ["FINANCE"])
    payment, _ = Payment.objects.get_or_create(
        enlistment=enlistment,
        defaults={
            "enlistment_amount": 0,
            "tuition_amount": 0,
            "amount": 0,
        },
    )
    payment.enlistment_amount = enlistment_amount
    payment.tuition_amount = tuition_amount
    payment.amount = tuition_amount
    payment.save(update_fields=["enlistment_amount", "tuition_amount", "amount"])
    log_history(
        actor=user,
        enlistment=enlistment,
        action=HistoryLog.Action.AMOUNT_SET,
        message=f"Set enlistment fee={enlistment_amount}, tuition fee={tuition_amount}.",
    )
    return payment

@transaction.atomic
def finance_record_payment(user, enlistment, amount, reference="", payment_kind=None):
    require_role(user, ["FINANCE"])
    if enlistment.status != Enlistment.Status.APPROVED_FOR_PAYMENT:
        raise ValidationError("Payment can be recorded only when enlistment is approved for payment.")

    payment, _ = Payment.objects.get_or_create(
        enlistment=enlistment,
        defaults={
            "enlistment_amount": 0,
            "tuition_amount": 0,
            "amount": 0,
        },
    )
    if amount <= 0:
        raise ValidationError("Payment amount must be greater than 0.")

    kind = (payment_kind or "").upper()
    if kind not in {"ENLISTMENT", "TUITION"}:
        ref_upper = (reference or "").upper()
        kind = "ENLISTMENT" if "DOWNPAYMENT" in ref_upper else "TUITION"

    if kind == "ENLISTMENT":
        expected_due = payment.enlistment_amount
        if expected_due <= 0:
            raise ValidationError("Enlistment fee is not set.")
        prior_paid = payment.enlistment_paid_amount
        new_total_paid = prior_paid + amount
        payment.enlistment_paid_amount = min(new_total_paid, expected_due)
        fully_paid = payment.enlistment_paid_amount >= expected_due
        payment.enlistment_paid = fully_paid
    else:
        if not payment.enlistment_paid:
            raise ValidationError("Tuition payment is allowed only after enlistment fee is fully paid.")
        expected_due = payment.tuition_amount
        if expected_due <= 0:
            raise ValidationError("Tuition fee is not set.")
        prior_paid = payment.tuition_paid_amount
        new_total_paid = prior_paid + amount
        payment.tuition_paid_amount = min(new_total_paid, expected_due)
        fully_paid = payment.tuition_paid_amount >= expected_due

    payment.amount = payment.tuition_amount
    payment.submitted_amount = amount
    payment.status = Payment.Status.SUCCESS if fully_paid else Payment.Status.PENDING
    payment.reference = reference
    payment.save(
        update_fields=[
            "amount",
            "submitted_amount",
            "status",
            "reference",
            "enlistment_paid_amount",
            "tuition_paid_amount",
            "enlistment_paid",
        ]
    )

    remaining_due_before = max(expected_due - prior_paid, Decimal("0.00"))
    overpayment = amount - remaining_due_before if amount > remaining_due_before else Decimal("0.00")
    credit_to_post = overpayment
    if credit_to_post > 0:
        acct, _ = StudentFinanceAccount.objects.get_or_create(student=enlistment.student, defaults={"balance": 0})
        acct.balance = acct.balance - credit_to_post
        acct.save(update_fields=["balance"])

    if kind == "TUITION" and fully_paid:
        enlistment.status = Enlistment.Status.ENROLLED
        enlistment.save(update_fields=["status", "updated_at"])
    log_history(
        actor=user,
        enlistment=enlistment,
        action=HistoryLog.Action.PAYMENT_RECORDED,
        message=(
            f"{kind.title()} payment recorded by finance: {amount}. Ref: {reference}"
            if reference
            else f"{kind.title()} payment recorded by finance: {amount}."
        ),
    )
    if kind == "TUITION" and fully_paid:
        log_history(
            actor=user,
            enlistment=enlistment,
            action=HistoryLog.Action.ENROLLED,
            message="Enrollment confirmed by finance.",
        )
    return enlistment, fully_paid, overpayment, kind



from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
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

    # Create payment record (amount is placeholder; fees can be computed later)
    Payment.objects.update_or_create(
        enlistment=enlistment,
        defaults={"amount": 0, "status": Payment.Status.PENDING},
    )
    return enlistment

@transaction.atomic
def student_mark_paid(student, enlistment, amount, reference=""):
    if enlistment.student_id != student.id:
        raise PermissionDenied("Not your enlistment.")
    if enlistment.status != Enlistment.Status.APPROVED_FOR_PAYMENT:
        raise ValidationError("Enlistment is not approved for payment.")

    payment, _ = Payment.objects.get_or_create(enlistment=enlistment, defaults={"amount": 0})
    expected_due = payment.amount if payment.amount and payment.amount > 0 else amount
    if amount < expected_due:
        raise ValidationError(f"Payment amount cannot be less than the amount due ({expected_due}).")
    if payment.amount == 0:
        payment.amount = expected_due
    payment.status = Payment.Status.SUCCESS
    payment.reference = reference
    payment.save(update_fields=["amount", "status", "reference"])

    overpayment = amount - expected_due
    if overpayment > 0:
        acct, _ = StudentFinanceAccount.objects.get_or_create(student=student, defaults={"balance": 0})
        acct.balance = acct.balance - overpayment
        acct.save(update_fields=["balance"])

    enlistment.status = Enlistment.Status.ENROLLED
    enlistment.save(update_fields=["status", "updated_at"])
    log_history(
        actor=student,
        enlistment=enlistment,
        action=HistoryLog.Action.PAYMENT_RECORDED,
        message=f"Payment recorded. Ref: {reference}" if reference else "Payment recorded.",
    )
    log_history(
        actor=student,
        enlistment=enlistment,
        action=HistoryLog.Action.ENROLLED,
        message="Enrollment confirmed.",
    )
    return enlistment

@transaction.atomic
def finance_set_amount(user, enlistment, amount):
    require_role(user, ["FINANCE"])
    payment, _ = Payment.objects.get_or_create(enlistment=enlistment, defaults={"amount": 0})
    payment.amount = amount
    payment.save(update_fields=["amount"])
    log_history(
        actor=user,
        enlistment=enlistment,
        action=HistoryLog.Action.AMOUNT_SET,
        message=f"Set amount to {amount}.",
    )
    return payment

@transaction.atomic
def finance_record_payment(user, enlistment, amount, reference=""):
    require_role(user, ["FINANCE"])
    if enlistment.status != Enlistment.Status.APPROVED_FOR_PAYMENT:
        raise ValidationError("Payment can be recorded only when enlistment is approved for payment.")

    payment, _ = Payment.objects.get_or_create(enlistment=enlistment, defaults={"amount": 0})
    expected_due = payment.amount if payment.amount and payment.amount > 0 else amount
    if amount < expected_due:
        raise ValidationError(f"Payment amount cannot be less than the amount due ({expected_due}).")
    if payment.amount == 0:
        payment.amount = expected_due
    payment.status = Payment.Status.SUCCESS
    payment.reference = reference
    payment.save(update_fields=["amount", "status", "reference"])

    overpayment = amount - expected_due
    if overpayment > 0:
        acct, _ = StudentFinanceAccount.objects.get_or_create(student=enlistment.student, defaults={"balance": 0})
        acct.balance = acct.balance - overpayment
        acct.save(update_fields=["balance"])

    enlistment.status = Enlistment.Status.ENROLLED
    enlistment.save(update_fields=["status", "updated_at"])
    log_history(
        actor=user,
        enlistment=enlistment,
        action=HistoryLog.Action.PAYMENT_RECORDED,
        message=f"Payment recorded by finance. Ref: {reference}" if reference else "Payment recorded by finance.",
    )
    log_history(
        actor=user,
        enlistment=enlistment,
        action=HistoryLog.Action.ENROLLED,
        message="Enrollment confirmed by finance.",
    )
    return enlistment



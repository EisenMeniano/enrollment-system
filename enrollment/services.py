from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from .models import Enlistment, Payment, EnlistmentSubject, Subject

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
def student_submit_enlistment(student, school_year, semester, notes=""):
    enlistment = Enlistment.objects.create(
        student=student,
        school_year=school_year,
        semester=semester,
        status=Enlistment.Status.SUBMITTED,
        notes=notes,
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
    return enlistment

@transaction.atomic
def adviser_return_for_revision(user, enlistment, reason):
    require_role(user, ["ADVISER"])
    if enlistment.status not in [Enlistment.Status.SUBMITTED, Enlistment.Status.FINANCE_APPROVED]:
        raise ValidationError("Enlistment is not in a state that can be returned.")
    enlistment.status = Enlistment.Status.RETURNED
    enlistment.hold_reason = reason
    enlistment.save(update_fields=["status", "hold_reason", "updated_at"])
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

    # Create payment record (amount is placeholder; fees can be computed later)
    Payment.objects.update_or_create(
        enlistment=enlistment,
        defaults={"amount": 0, "status": Payment.Status.PENDING},
    )
    return enlistment

@transaction.atomic
def student_mark_paid(student, enlistment, reference=""):
    if enlistment.student_id != student.id:
        raise PermissionDenied("Not your enlistment.")
    if enlistment.status != Enlistment.Status.APPROVED_FOR_PAYMENT:
        raise ValidationError("Enlistment is not approved for payment.")

    payment, _ = Payment.objects.get_or_create(enlistment=enlistment, defaults={"amount": 0})
    payment.status = Payment.Status.SUCCESS
    payment.reference = reference
    payment.save(update_fields=["status", "reference"])

    enlistment.status = Enlistment.Status.ENROLLED
    enlistment.save(update_fields=["status", "updated_at"])
    return enlistment

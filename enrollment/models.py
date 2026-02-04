from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL

class Subject(models.Model):
    code = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=200)
    units = models.PositiveSmallIntegerField(default=3)

    def __str__(self):
        return f"{self.code} - {self.title}"

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

class SchoolYear(models.Model):
    label = models.CharField(max_length=20, unique=True)  # e.g. 2025-2026
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-label"]

    def __str__(self):
        return self.label

class Semester(models.Model):
    name = models.CharField(max_length=20, unique=True)  # e.g. 1st, 2nd, Summer
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

class StudentFinanceAccount(models.Model):
    student = models.OneToOneField(User, on_delete=models.CASCADE, related_name="finance_account")
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.student} balance={self.balance}"

class PreviousTermSubject(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="previous_subjects")
    school_year = models.CharField(max_length=20)   # e.g. 2025-2026
    semester = models.CharField(max_length=20)      # e.g. 1st, 2nd, Summer
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    grade = models.CharField(max_length=20, blank=True)
    passed = models.BooleanField(default=True)

    class Meta:
        ordering = ["-school_year", "semester", "subject__code"]

    def __str__(self):
        return f"{self.student} {self.subject.code} ({self.school_year} {self.semester})"

class Enlistment(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted (Pending Adviser)"
        RETURNED = "RETURNED", "Returned for Revision"
        FINANCE_REVIEW = "FINANCE_REVIEW", "Pending Admin/Finance Review"
        FINANCE_HOLD_BALANCE = "FINANCE_HOLD_BALANCE", "Hold (Unpaid Balance)"
        FINANCE_HOLD_ACADEMIC = "FINANCE_HOLD_ACADEMIC", "Hold (Academic Issue)"
        FINANCE_APPROVED = "FINANCE_APPROVED", "Cleared by Admin/Finance"
        APPROVED_FOR_PAYMENT = "APPROVED_FOR_PAYMENT", "Approved for Payment"
        ENROLLED = "ENROLLED", "Enrollment Confirmed"
        REJECTED = "REJECTED", "Rejected"

    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="enlistments")
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, null=True, blank=True, related_name="enlistments"
    )
    school_year = models.CharField(max_length=20)
    semester = models.CharField(max_length=20)
    status = models.CharField(max_length=40, choices=Status.choices, default=Status.SUBMITTED)
    notes = models.TextField(blank=True)            # student notes
    hold_reason = models.TextField(blank=True)      # finance/adviser reason

    adviser_preapproved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="preapproved_enlistments"
    )
    finance_checked_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="finance_checked_enlistments"
    )
    adviser_final_approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="final_approved_enlistments"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student} {self.school_year} {self.semester} ({self.status})"

class EnlistmentSubject(models.Model):
    enlistment = models.ForeignKey(Enlistment, on_delete=models.CASCADE, related_name="next_subjects")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)

    class Meta:
        unique_together = ("enlistment", "subject")

    def __str__(self):
        return f"{self.enlistment} -> {self.subject.code}"

class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"

    enlistment = models.OneToOneField(Enlistment, on_delete=models.CASCADE, related_name="payment")
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reference = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.enlistment} payment={self.status}"

class HistoryLog(models.Model):
    class Action(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        RETURNED = "RETURNED", "Returned for Revision"
        PREAPPROVED = "PREAPPROVED", "Adviser Pre-Approved"
        FINANCE_REVIEWED = "FINANCE_REVIEWED", "Finance Reviewed"
        FINANCE_HELD = "FINANCE_HELD", "Finance Hold"
        AMOUNT_SET = "AMOUNT_SET", "Amount Set"
        FINAL_APPROVED = "FINAL_APPROVED", "Adviser Final Approved"
        PAYMENT_RECORDED = "PAYMENT_RECORDED", "Payment Recorded"
        ENROLLED = "ENROLLED", "Enrolled"

    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="history_actions")
    enlistment = models.ForeignKey(Enlistment, on_delete=models.SET_NULL, null=True, blank=True, related_name="history_logs")
    action = models.CharField(max_length=50, choices=Action.choices)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_action_display()} by {self.actor} at {self.created_at}"

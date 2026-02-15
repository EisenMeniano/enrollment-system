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

class Program(models.Model):
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
    program = models.ForeignKey(
        Program, on_delete=models.PROTECT, null=True, blank=True, related_name="enlistments"
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
        SUBMITTED = "SUBMITTED", "Submitted for Finance Approval"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"

    enlistment = models.OneToOneField(Enlistment, on_delete=models.CASCADE, related_name="payment")
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    submitted_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
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


class EnrollmentWindow(models.Model):
    is_open = models.BooleanField(default=True)
    message = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Enrollment Window"
        verbose_name_plural = "Enrollment Window"

    def __str__(self):
        return "Open" if self.is_open else "Closed"

    @classmethod
    def get_solo(cls):
        obj = cls.objects.first()
        if not obj:
            obj = cls.objects.create(is_open=True, message="")
        return obj


class StudentProfileMenuItem(models.Model):
    label = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    url = models.CharField(max_length=200)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "label"]

    def __str__(self):
        return self.label

    @classmethod
    def get_menu(cls):
        if cls.objects.exists():
            return cls.objects.filter(is_active=True).order_by("order", "label")
        defaults = [
            ("personal", "Personal Details", "/enrollment/student/profile/"),
            ("address", "Address Details", "/enrollment/student/profile/address/"),
            ("course", "Course Details", "/enrollment/student/profile/course/"),
            ("photo", "Photo Signature", "/enrollment/student/profile/photo/"),
            ("enlisted", "Enlisted Subjects", "/enrollment/student/profile/enlisted/"),
            ("grade", "Grade", "/enrollment/student/profile/grade/"),
            ("schedule", "Class Schedule", "/enrollment/student/profile/schedule/"),
            ("attendance", "Attendance", "/enrollment/student/profile/attendance/"),
            ("overall", "Overall Result", "/enrollment/student/profile/overall/"),
            ("permit", "Exam Permit", "/enrollment/student/profile/permit/"),
            ("document", "Document", "/enrollment/student/profile/document/"),
            ("exam_schedule", "Exam Schedule", "/enrollment/student/profile/exam-schedule/"),
            ("deferment", "Apply Deferment", "/enrollment/student/profile/deferment/"),
            ("curriculum", "Curriculum Progressions", "/enrollment/student/profile/curriculum/"),
        ]
        for order, (slug, label, url) in enumerate(defaults, start=1):
            cls.objects.create(slug=slug, label=label, url=url, order=order, is_active=True)
        return cls.objects.filter(is_active=True).order_by("order", "label")


class AttendanceRecord(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="attendance_records")
    session = models.ForeignKey(SchoolYear, on_delete=models.SET_NULL, null=True, blank=True)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    subject_type = models.CharField(max_length=50, blank=True)
    total_classes = models.PositiveSmallIntegerField(default=0)
    total_present = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["subject__code"]

    @property
    def attendance_percent(self):
        if self.total_classes <= 0:
            return 0
        return round((self.total_present / self.total_classes) * 100, 2)

    def __str__(self):
        return f"{self.student} {self.subject.code} ({self.session})"


class OverallResult(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="overall_results")
    session = models.ForeignKey(SchoolYear, on_delete=models.SET_NULL, null=True, blank=True)
    semester_name = models.CharField(max_length=20, blank=True)
    total_subjects = models.PositiveSmallIntegerField(default=0)
    gwa = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    result_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-result_date", "-id"]

    def __str__(self):
        return f"{self.student} {self.semester_name} {self.session}"


class OverallResultItem(models.Model):
    result = models.ForeignKey(OverallResult, on_delete=models.CASCADE, related_name="items")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    subject_type = models.CharField(max_length=50, blank=True)
    units = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    final_grade = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    status = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["subject__code"]

    def __str__(self):
        return f"{self.result} {self.subject.code}"


class ExamPermit(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="exam_permits")
    session = models.ForeignKey(SchoolYear, on_delete=models.SET_NULL, null=True, blank=True)
    semester_name = models.CharField(max_length=20, blank=True)
    period_no = models.CharField(max_length=20, blank=True)
    file = models.FileField(upload_to="permits/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student} {self.session} {self.semester_name}"


class ExamSchedule(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="exam_schedules")
    session = models.ForeignKey(SchoolYear, on_delete=models.SET_NULL, null=True, blank=True)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    exam_date = models.DateField(null=True, blank=True)
    exam_time = models.CharField(max_length=50, blank=True)
    room = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["exam_date", "exam_time"]

    def __str__(self):
        return f"{self.student} {self.subject.code}"


class DefermentRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="deferment_requests")
    session = models.ForeignKey(SchoolYear, on_delete=models.SET_NULL, null=True, blank=True)
    num_semesters = models.PositiveSmallIntegerField(default=1)
    deferment_type = models.CharField(max_length=50, blank=True)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student} {self.deferment_type} {self.status}"


class CurriculumProgressSummary(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="curriculum_summaries")
    session = models.ForeignKey(SchoolYear, on_delete=models.SET_NULL, null=True, blank=True)
    semester_name = models.CharField(max_length=20, blank=True)
    earned_credits = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    registered_credits = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    remaining_credits = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    total_credits = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    sgpa = models.DecimalField(max_digits=4, decimal_places=2, default=0)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.student} {self.session}"


class CurriculumProgressCourse(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="curriculum_courses")
    session = models.ForeignKey(SchoolYear, on_delete=models.SET_NULL, null=True, blank=True)
    semester_name = models.CharField(max_length=20, blank=True)
    curriculum_pattern = models.CharField(max_length=50, blank=True)
    course_name = models.CharField(max_length=150, blank=True)
    course_type = models.CharField(max_length=50, blank=True)
    credits = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    grade = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    status = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["session", "semester_name", "course_name"]

    def __str__(self):
        return f"{self.student} {self.course_name}"

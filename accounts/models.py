from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "STUDENT", "Student"
        ADVISER = "ADVISER", "Adviser"
        FINANCE = "FINANCE", "Admin/Finance"

    student_number = models.CharField(max_length=50, unique=True, verbose_name="student number")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)

    def __str__(self):
        return f"{self.student_number} ({self.role})"

    USERNAME_FIELD = "student_number"
    REQUIRED_FIELDS = ["username", "email"]

    @property
    def program(self):
        try:
            return self.student_profile.program
        except StudentProfile.DoesNotExist:
            return ""

class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
    program = models.CharField(max_length=100, blank=True)
    year_level = models.PositiveSmallIntegerField(default=1)
    campus = models.CharField(max_length=100, blank=True)
    college = models.CharField(max_length=150, blank=True)
    curriculum = models.CharField(max_length=150, blank=True)
    middle_name = models.CharField(max_length=100, blank=True)
    extension_name = models.CharField(max_length=50, blank=True)
    gender = models.CharField(max_length=20, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    place_of_birth = models.CharField(max_length=150, blank=True)
    civil_status = models.CharField(max_length=50, blank=True)
    citizenship = models.CharField(max_length=50, blank=True)
    dual_citizenship = models.CharField(max_length=50, blank=True)
    religion = models.CharField(max_length=50, blank=True)
    mobile_no = models.CharField(max_length=30, blank=True)
    facebook_name = models.CharField(max_length=150, blank=True)
    facebook_link = models.URLField(max_length=300, blank=True)
    # Address (current)
    current_address_line = models.CharField(max_length=200, blank=True)
    current_country = models.CharField(max_length=100, blank=True)
    current_province = models.CharField(max_length=100, blank=True)
    current_city = models.CharField(max_length=100, blank=True)
    current_postal_code = models.CharField(max_length=20, blank=True)
    # Address (permanent)
    same_as_current = models.BooleanField(default=True)
    permanent_address_line = models.CharField(max_length=200, blank=True)
    permanent_country = models.CharField(max_length=100, blank=True)
    permanent_province = models.CharField(max_length=100, blank=True)
    permanent_city = models.CharField(max_length=100, blank=True)
    permanent_postal_code = models.CharField(max_length=20, blank=True)

    # Course details
    intake = models.CharField(max_length=50, blank=True)
    learning_modality = models.CharField(max_length=50, blank=True)
    advisor_name = models.CharField(max_length=150, blank=True)
    mentor_name = models.CharField(max_length=150, blank=True)

    # Photo / signature
    photo_file = models.FileField(upload_to="photos/", blank=True, null=True)
    signature_file = models.FileField(upload_to="signatures/", blank=True, null=True)

    def __str__(self):
        return f"{self.user.student_number} - {self.user.get_full_name() or self.user.username}"

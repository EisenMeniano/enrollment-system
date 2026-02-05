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

    def __str__(self):
        return f"{self.user.student_number} - {self.user.get_full_name() or self.user.username}"

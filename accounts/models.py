from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "STUDENT", "Student"
        ADVISER = "ADVISER", "Adviser"
        FINANCE = "FINANCE", "Admin/Finance"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)

    def __str__(self):
        return f"{self.username} ({self.role})"

class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
    student_number = models.CharField(max_length=50, unique=True)
    program = models.CharField(max_length=100, blank=True)
    year_level = models.PositiveSmallIntegerField(default=1)

    def __str__(self):
        return f"{self.student_number} - {self.user.get_full_name() or self.user.username}"

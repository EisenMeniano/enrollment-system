from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, StudentProfile

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Identifiers", {"fields": ("student_number",)}),
        ("Role", {"fields": ("role",)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {"fields": ("student_number",)}),
    )
    list_display = ("student_number", "username", "email", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active")

@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "program", "year_level")
    search_fields = ("user__student_number", "user__username", "user__first_name", "user__last_name")

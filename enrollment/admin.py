from django.contrib import admin
from types import MethodType
from .models import (
    Subject,
    StudentFinanceAccount,
    PreviousTermSubject,
    Enlistment,
    EnlistmentSubject,
    Payment,
    Category,
    SchoolYear,
    Semester,
    Program,
    EnrollmentWindow,
    AttendanceRecord,
    OverallResult,
    OverallResultItem,
    ExamPermit,
    ExamSchedule,
    DefermentRequest,
    CurriculumProgressSummary,
    CurriculumProgressCourse,
    StudentProfileMenuItem,
)

admin.site.register(Subject)
admin.site.register(Category)
admin.site.register(Program)
admin.site.register(EnrollmentWindow)
admin.site.register(StudentProfileMenuItem)
admin.site.register(SchoolYear)
admin.site.register(Semester)
admin.site.register(AttendanceRecord)
admin.site.register(ExamPermit)
admin.site.register(ExamSchedule)
admin.site.register(DefermentRequest)
admin.site.register(CurriculumProgressSummary)
admin.site.register(CurriculumProgressCourse)
admin.site.register(StudentFinanceAccount)
admin.site.register(PreviousTermSubject)

class EnlistmentSubjectInline(admin.TabularInline):
    model = EnlistmentSubject
    extra = 0

@admin.register(Enlistment)
class EnlistmentAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "school_year", "semester", "status", "created_at")
    list_filter = ("status", "school_year", "semester")
    search_fields = ("student__student_number", "student__username", "student__email")
    inlines = [EnlistmentSubjectInline]

admin.site.register(Payment)

class OverallResultItemInline(admin.TabularInline):
    model = OverallResultItem
    extra = 0

@admin.register(OverallResult)
class OverallResultAdmin(admin.ModelAdmin):
    list_display = ("student", "session", "semester_name", "gwa", "result_date")
    list_filter = ("session", "semester_name")
    inlines = [OverallResultItemInline]

# ---- Admin sidebar grouping: move student-profile related models into their own section
_original_get_app_list = admin.site.get_app_list

def _custom_get_app_list(self, request):
    app_list = _original_get_app_list(request)
    enrollment_app = None
    enrollment_index = None
    for idx, app in enumerate(app_list):
        if app.get("app_label") == "enrollment":
            enrollment_app = app
            enrollment_index = idx
            break
    if not enrollment_app:
        return app_list

    student_model_names = {
        "studentprofilemenuitem",
        "attendancerecord",
        "overallresult",
        "exampermit",
        "examschedule",
        "defermentrequest",
        "curriculumprogresssummary",
        "curriculumprogresscourse",
    }

    student_models = []
    remaining_models = []
    for m in enrollment_app.get("models", []):
        obj_name = (m.get("object_name") or "").lower()
        if obj_name in student_model_names:
            student_models.append(m)
        else:
            remaining_models.append(m)

    if student_models:
        enrollment_app["models"] = remaining_models
        student_app = {
            "name": "Student Profile",
            "app_label": "student_profile",
            "app_url": enrollment_app.get("app_url", ""),
            "has_module_perms": True,
            "models": student_models,
        }
        insert_at = enrollment_index if enrollment_index is not None else 0
        app_list.insert(insert_at, student_app)

    return app_list

admin.site.get_app_list = MethodType(_custom_get_app_list, admin.site)

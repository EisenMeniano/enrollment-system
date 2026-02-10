from django.urls import path
from . import views

app_name = "enrollment"

urlpatterns = [
    # Student
    path("student/", views.student_dashboard, name="student_dashboard"),
    path("student/profile/", views.student_profile_personal, name="student_profile_personal"),
    path("student/profile/address/", views.student_profile_address, name="student_profile_address"),
    path("student/profile/course/", views.student_profile_course, name="student_profile_course"),
    path("student/profile/photo/", views.student_profile_photo, name="student_profile_photo"),
    path("student/profile/enlisted/", views.student_profile_enlisted, name="student_profile_enlisted"),
    path("student/profile/grade/", views.student_profile_grade, name="student_profile_grade"),
    path("student/profile/schedule/", views.student_profile_schedule, name="student_profile_schedule"),
    path("student/profile/attendance/", views.student_profile_attendance, name="student_profile_attendance"),
    path("student/profile/overall/", views.student_profile_overall, name="student_profile_overall"),
    path("student/profile/permit/", views.student_profile_permit, name="student_profile_permit"),
    path("student/profile/document/", views.student_profile_document, name="student_profile_document"),
    path("student/profile/exam-schedule/", views.student_profile_exam_schedule, name="student_profile_exam_schedule"),
    path("student/profile/deferment/", views.student_profile_deferment, name="student_profile_deferment"),
    path("student/profile/curriculum/", views.student_profile_curriculum, name="student_profile_curriculum"),
    path("student/new/", views.student_enlistment_create, name="enlistment_create"),
    path("student/subjects/<int:pk>/", views.student_subject_select, name="student_subject_select"),
    path("student/pay/<int:pk>/", views.student_pay, name="student_pay"),

    # Adviser
    path("adviser/", views.adviser_dashboard, name="adviser_dashboard"),
    path("adviser/preapprove/<int:pk>/", views.adviser_preapprove_view, name="adviser_preapprove"),
    path("adviser/return/<int:pk>/", views.adviser_return_view, name="adviser_return"),
    path("adviser/final-approve/<int:pk>/", views.adviser_final_approve_view, name="adviser_final_approve"),

    # Finance
    path("finance/", views.finance_dashboard, name="finance_dashboard"),
    path("finance/review/<int:pk>/", views.finance_review_view, name="finance_review"),
    path("finance/amount/<int:pk>/", views.finance_set_amount_view, name="finance_set_amount"),
    path("finance/enrollment-toggle/", views.finance_toggle_enrollment, name="finance_toggle_enrollment"),

    # Shared
    path("enlistment/<int:pk>/", views.enlistment_detail, name="enlistment_detail"),
    path("history/", views.history_log, name="history_log"),
]

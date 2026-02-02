from django.urls import path
from . import views

app_name = "enrollment"

urlpatterns = [
    # Student
    path("student/", views.student_dashboard, name="student_dashboard"),
    path("student/new/", views.student_enlistment_create, name="enlistment_create"),
    path("student/pay/<int:pk>/", views.student_pay, name="student_pay"),

    # Adviser
    path("adviser/", views.adviser_dashboard, name="adviser_dashboard"),
    path("adviser/preapprove/<int:pk>/", views.adviser_preapprove_view, name="adviser_preapprove"),
    path("adviser/return/<int:pk>/", views.adviser_return_view, name="adviser_return"),
    path("adviser/final-approve/<int:pk>/", views.adviser_final_approve_view, name="adviser_final_approve"),

    # Finance
    path("finance/", views.finance_dashboard, name="finance_dashboard"),
    path("finance/review/<int:pk>/", views.finance_review_view, name="finance_review"),

    # Shared
    path("enlistment/<int:pk>/", views.enlistment_detail, name="enlistment_detail"),
]

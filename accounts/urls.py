from django.urls import path
from django.contrib.auth import views as auth_views
from .views import PasswordChangeNotifyView, profile_view

app_name = "accounts"

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="accounts/login.html",
            redirect_authenticated_user=True,  # optional: sends logged-in users away from login
        ),
        name="login",
    ),
    path("password/change/", PasswordChangeNotifyView.as_view(), name="password_change"),
    path("profile/", profile_view, name="profile"),
    # ✅ Logout should be POST from the template (recommended)
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]

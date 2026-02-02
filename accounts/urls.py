from django.urls import path
from django.contrib.auth import views as auth_views

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
    # ✅ Logout should be POST from the template (recommended)
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]

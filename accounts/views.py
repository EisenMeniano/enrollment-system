from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.core.mail import send_mail
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .forms import UserProfileForm


class PasswordChangeNotifyView(auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("dashboard")

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.request.user
        if user.email:
            send_mail(
                subject="Your password was changed",
                message=(
                    f"Hi {user.get_full_name() or user.student_number},\n\n"
                    "This is a confirmation that your account password was changed.\n"
                    "If you did not make this change, please contact the admin immediately."
                ),
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=[user.email],
                fail_silently=True,
            )
        else:
            messages.warning(self.request, "Password changed, but no email is set for this account.")
        messages.success(self.request, "Password changed successfully.")
        return response


@login_required
def profile_view(request):
    if request.method == "POST":
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("accounts:profile")
    else:
        form = UserProfileForm(instance=request.user)
    return render(request, "accounts/profile.html", {"form": form})

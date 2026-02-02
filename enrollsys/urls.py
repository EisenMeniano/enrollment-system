from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from enrollment.views import dashboard

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("", dashboard, name="dashboard"),
    path("enrollment/", include("enrollment.urls")),
]

# In development, serve media via Django.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

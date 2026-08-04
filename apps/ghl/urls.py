from django.urls import path

from .views import health_check, oauth_callback


app_name = "ghl"

urlpatterns = [
    path("oauth/callback/", oauth_callback, name="oauth-callback"),
    path("health/", health_check, name="health-check"),
]
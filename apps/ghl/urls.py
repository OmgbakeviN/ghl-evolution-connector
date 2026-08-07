from django.urls import path

from .views import (
    health_check, oauth_callback, user_context, 
    oauth_success
)

app_name = "ghl"

urlpatterns = [
    path("oauth/callback/", oauth_callback, name="oauth-callback"),
    path("health/", health_check, name="health-check"),
    path("user-context/", user_context, name="user-context"),
    path("oauth/success/", oauth_success, name="oauth-success"),
]
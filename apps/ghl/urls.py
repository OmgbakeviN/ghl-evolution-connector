from django.urls import path

from .views import (
    health_check, oauth_callback, user_context, 
    oauth_success, embedded_contacts,
)

app_name = "ghl"

urlpatterns = [
    path("oauth/callback/", oauth_callback, name="oauth-callback"),
    path("health/", health_check, name="health-check"),
    path("user-context/", user_context, name="user-context"),
    path("oauth/success/", oauth_success, name="oauth-success"),
    path("embedded/contacts/", embedded_contacts, name="embedded-contacts"),
]
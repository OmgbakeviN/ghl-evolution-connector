from django.urls import path

from .views import (
    instance_status, whatsapp_dashboard, embedded_dashboard,
    embedded_instance_status, instance_status, whatsapp_dashboard, 
    evolution_webhook,
)


app_name = "evolution"

urlpatterns = [
    path(
        "dashboard/<str:location_id>/",
        whatsapp_dashboard,
        name="dashboard",
    ),
    path(
        "api/status/<str:location_id>/",
        instance_status,
        name="instance-status",
    ),
    path(
        "embedded/",
        embedded_dashboard,
        name="embedded-dashboard",
    ),
    path(
        "api/embedded/status/",
        embedded_instance_status,
        name="embedded-instance-status",
    ),
]
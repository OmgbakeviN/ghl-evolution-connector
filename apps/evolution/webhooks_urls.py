from django.urls import path

from .views import evolution_webhook


urlpatterns = [
    path(
        "webhooks/<str:webhook_secret>/",
        evolution_webhook,
        name="evolution-webhook",
    ),
]
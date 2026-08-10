from django.contrib import admin

from .models import EvolutionInstance, WebhookEvent


@admin.register(EvolutionInstance)
class EvolutionInstanceAdmin(admin.ModelAdmin):
    list_display = (
        "instance_name",
        "installation",
        "integration",
        "status",
        "phone_number",
        "is_active",
        "created_at",
    )

    list_filter = (
        "status",
        "integration",
        "is_active",
    )

    search_fields = (
        "instance_name",
        "remote_instance_id",
        "phone_number",
        "installation__location_id",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "connected_at",
        "last_synced_at",
    )

    # La clé de l'instance ne doit pas être affichée
    # directement dans l'administration.
    exclude = (
        "instance_api_key",
    )

@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = (
        "event_type",
        "instance",
        "event_id",
        "status",
        "attempts",
        "received_at",
    )

    list_filter = (
        "event_type",
        "status",
        "received_at",
    )

    search_fields = (
        "event_id",
        "instance__instance_name",
        "instance__installation__location_id",
    )

    readonly_fields = (
        "payload",
        "deduplication_key",
        "received_at",
        "processed_at",
    )
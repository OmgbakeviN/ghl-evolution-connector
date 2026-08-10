from django.contrib import admin
from .models import BulkCampaign, BulkCampaignRecipient


class BulkCampaignRecipientInline(admin.TabularInline):
    model = BulkCampaignRecipient
    extra = 0
    raw_id_fields = ("campaign",)
    readonly_fields = (
        "ghl_contact_id",
        "first_name",
        "last_name",
        "email",
        "phone",
        "normalized_phone",
        "is_on_whatsapp",
        "whatsapp_jid",
        "whatsapp_checked_at",
        "whatsapp_check_error",
        "rendered_message",
        "status",
        "evolution_message_id",
        "attempts",
        "last_error",
        "sent_at",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(BulkCampaign)
class BulkCampaignAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "installation",
        "status",
        "total_contacts",
        "sent_count",
        "failed_count",
        "created_at",
    )
    list_filter = ("status", "created_at", "updated_at")
    search_fields = (
        "name",
        "installation__id",
        "created_by_highlevel_user_id",
    )
    readonly_fields = (
        "total_contacts",
        "validated_count",
        "not_on_whatsapp_count",
        "validation_error_count",
        "sent_count",
        "failed_count",
        "skipped_count",
        "started_at",
        "completed_at",
        "created_at",
        "updated_at",
    )
    raw_id_fields = ("installation",)
    inlines = [BulkCampaignRecipientInline]
    fieldsets = (
        (
            "General Information",
            {
                "fields": (
                    "name",
                    "installation",
                    "status",
                    "created_by_highlevel_user_id",
                    "message_template",
                )
            },
        ),
        (
            "Metrics & Statistics",
            {
                "fields": (
                    "total_contacts",
                    "validated_count",
                    "not_on_whatsapp_count",
                    "validation_error_count",
                    "sent_count",
                    "failed_count",
                    "skipped_count",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "started_at",
                    "completed_at",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )


@admin.register(BulkCampaignRecipient)
class BulkCampaignRecipientAdmin(admin.ModelAdmin):
    list_display = (
        "ghl_contact_id",
        "campaign",
        "phone",
        "is_on_whatsapp",
        "status",
        "attempts",
        "sent_at",
    )
    list_filter = ("status", "is_on_whatsapp", "created_at")
    search_fields = (
        "ghl_contact_id",
        "first_name",
        "last_name",
        "email",
        "phone",
        "normalized_phone",
        "evolution_message_id",
        "campaign__name",
    )
    raw_id_fields = ("campaign",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            "Campaign & Contact Details",
            {
                "fields": (
                    "campaign",
                    "ghl_contact_id",
                    "first_name",
                    "last_name",
                    "email",
                )
            },
        ),
        (
            "Phone & WhatsApp Verification",
            {
                "fields": (
                    "phone",
                    "normalized_phone",
                    "is_on_whatsapp",
                    "whatsapp_jid",
                    "whatsapp_checked_at",
                    "whatsapp_check_error",
                )
            },
        ),
        (
            "Delivery Status & Logs",
            {
                "fields": (
                    "status",
                    "rendered_message",
                    "evolution_message_id",
                    "attempts",
                    "last_error",
                    "sent_at",
                )
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at")},
        ),
    )

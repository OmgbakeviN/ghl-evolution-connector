from django.contrib import admin

from .models import GHLInstallation


@admin.register(GHLInstallation)
class GHLInstallationAdmin(admin.ModelAdmin):
    list_display = (
        "location_id",
        "company_id",
        "user_type",
        "is_active",
        "expires_at",
        "installed_at",
    )

    search_fields = (
        "location_id",
        "company_id",
        "user_id",
    )

    readonly_fields = (
        "installed_at",
        "updated_at",
    )

    # Évite d'afficher les tokens directement dans la liste.
    exclude = (
        "access_token",
        "refresh_token",
    )
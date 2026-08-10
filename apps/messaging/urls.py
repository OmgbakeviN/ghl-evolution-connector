from django.urls import path

from .views import ( create_bulk_campaign_draft,
    validate_bulk_campaign,
    bulk_campaign_status,
    start_bulk_campaign,
    list_bulk_campaigns
)


app_name = "messaging"


urlpatterns = [
    path(
        "campaigns/draft/",
        create_bulk_campaign_draft,
        name="create-campaign-draft",
    ),
    path(
        "campaigns/<int:campaign_id>/validate/",
        validate_bulk_campaign,
        name="validate-campaign",
    ),
    path(
        "campaigns/<int:campaign_id>/start/",
        start_bulk_campaign,
        name="start-campaign",
    ),
    path(
        "campaigns/<int:campaign_id>/status/",
        bulk_campaign_status,
        name="campaign-status",
    ),
    path(
        "campaigns/",
        list_bulk_campaigns,
        name="list-campaigns",
    ),
]
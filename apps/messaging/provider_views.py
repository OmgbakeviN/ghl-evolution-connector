import json

from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.evolution.client import (
    EvolutionAPIError,
    EvolutionClient,
)
from apps.evolution.models import (
    EvolutionInstance,
)
from apps.ghl.models import (
    GHLInstallation,
)

from .ghl_provider_security import (
    verify_ghl_provider_signature,
)
from .models import (
    BulkCampaignRecipient,
)
from .services import (
    extract_evolution_message_id,
    refresh_campaign_progress,
)

@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def ghl_provider_outbound(
    request,
):
    """
    Delivery URL du Custom Conversation Provider GHL.

    HighLevel crée d'abord le message dans Conversations,
    puis appelle cet endpoint pour que notre provider
    effectue réellement l'envoi.
    """

    raw_body = request.body

    signature = request.headers.get(
        "X-GHL-Signature",
        "",
    )


    if not verify_ghl_provider_signature(
        raw_body,
        signature,
    ):
        return Response(
            {
                "success": False,
                "message": (
                    "Signature HighLevel invalide."
                ),
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )


    try:

        payload = json.loads(
            raw_body.decode("utf-8")
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):

        return Response(
            {
                "success": False,
                "message": "Payload JSON invalide.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


    location_id = str(
        payload.get("locationId")
        or ""
    ).strip()

    contact_id = str(
        payload.get("contactId")
        or ""
    ).strip()

    ghl_message_id = str(
        payload.get("messageId")
        or ""
    ).strip()

    message = str(
        payload.get("message")
        or ""
    ).strip()

    phone = str(
        payload.get("phone")
        or ""
    ).strip()

    message_type = str(
        payload.get("type")
        or ""
    ).strip()


    if message_type.upper() != "SMS":

        return Response(
            {
                "success": True,
                "ignored": True,
                "reason": (
                    "Type provider non supporté."
                ),
            }
        )


    if not location_id:

        return Response(
            {
                "success": False,
                "message": (
                    "locationId absent."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


    if not contact_id:

        return Response(
            {
                "success": False,
                "message": (
                    "contactId absent."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


    if not message:

        return Response(
            {
                "success": False,
                "message": (
                    "Message absent."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


    installation = (
        GHLInstallation.objects
        .filter(
            location_id=location_id,
            is_active=True,
        )
        .first()
    )


    if installation is None:

        return Response(
            {
                "success": False,
                "message": (
                    "Installation GHL introuvable."
                ),
            },
            status=status.HTTP_404_NOT_FOUND,
        )


    #
    # 1. Recherche exacte par messageId.
    #

    recipient = None

    if ghl_message_id:

        recipient = (
            BulkCampaignRecipient.objects
            .select_related(
                "campaign",
                "campaign__installation",
            )
            .filter(
                campaign__installation=(
                    installation
                ),
                ghl_message_id=(
                    ghl_message_id
                ),
            )
            .first()
        )


    #
    # 2. Fallback.
    #
    # Le webhook peut arriver avant que
    # send_provider_message() ait enregistré
    # le messageId GHL dans PostgreSQL.
    #

    if recipient is None:

        recipient = (
            BulkCampaignRecipient.objects
            .select_related(
                "campaign",
                "campaign__installation",
            )
            .filter(
                campaign__installation=(
                    installation
                ),
                ghl_contact_id=contact_id,
                status=(
                    BulkCampaignRecipient
                    .Status.PROCESSING
                ),
                rendered_message=message,
            )
            .order_by(
                "-updated_at"
            )
            .first()
        )


    if recipient is None:

        #
        # Pour l'instant notre provider
        # ne traite que les messages issus
        # du moteur bulk.
        #
        return Response(
            {
                "success": False,
                "message": (
                    "Aucun destinataire bulk "
                    "correspondant."
                ),
            },
            status=status.HTTP_409_CONFLICT,
        )


    #
    # Protection contre les webhooks
    # dupliqués.
    #

    if (
        recipient.status
        == BulkCampaignRecipient.Status.SENT
    ):

        return Response(
            {
                "success": True,
                "duplicate": True,
                "recipient_id": recipient.pk,
            }
        )


    if ghl_message_id:

        recipient.ghl_message_id = (
            ghl_message_id
        )

    recipient.ghl_history_synced_at = (
        recipient.ghl_history_synced_at
        or timezone.now()
    )

    recipient.save(
        update_fields=[
            "ghl_message_id",
            "ghl_history_synced_at",
            "updated_at",
        ]
    )


    try:

        evolution_instance = (
            installation.evolution_instance
        )

    except EvolutionInstance.DoesNotExist:

        error_message = (
            "Aucune instance Evolution "
            "associée au sous-compte."
        )

        recipient.status = (
            BulkCampaignRecipient.Status.FAILED
        )

        recipient.provider_delivery_status = (
            BulkCampaignRecipient
            .ProviderDeliveryStatus.FAILED
        )

        recipient.last_error = error_message

        recipient.save(
            update_fields=[
                "status",
                "provider_delivery_status",
                "last_error",
                "updated_at",
            ]
        )

        refresh_campaign_progress(
            recipient.campaign_id
        )

        return Response(
            {
                "success": False,
                "message": error_message,
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )


    if (
        evolution_instance.status
        != EvolutionInstance.Status.OPEN
    ):

        error_message = (
            "WhatsApp est déconnecté."
        )

        recipient.status = (
            BulkCampaignRecipient.Status.FAILED
        )

        recipient.provider_delivery_status = (
            BulkCampaignRecipient
            .ProviderDeliveryStatus.FAILED
        )

        recipient.last_error = error_message

        recipient.save(
            update_fields=[
                "status",
                "provider_delivery_status",
                "last_error",
                "updated_at",
            ]
        )

        refresh_campaign_progress(
            recipient.campaign_id
        )

        return Response(
            {
                "success": False,
                "message": error_message,
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )


    #
    # On préfère le numéro déjà validé
    # dans PostgreSQL.
    #

    destination_number = (
        recipient.normalized_phone
    )


    evolution_client = EvolutionClient()


    try:

        evolution_response = (
            evolution_client.send_text(
                instance_name=(
                    evolution_instance
                    .instance_name
                ),
                number=(
                    destination_number
                ),
                text=message,
                delay_ms=1000,
            )
        )

    except EvolutionAPIError as exc:

        recipient.status = (
            BulkCampaignRecipient.Status.FAILED
        )

        recipient.provider_delivery_status = (
            BulkCampaignRecipient
            .ProviderDeliveryStatus.FAILED
        )

        recipient.last_error = str(exc)

        recipient.save(
            update_fields=[
                "status",
                "provider_delivery_status",
                "last_error",
                "updated_at",
            ]
        )

        refresh_campaign_progress(
            recipient.campaign_id
        )

        return Response(
            {
                "success": False,
                "message": str(exc),
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )


    evolution_message_id = (
        extract_evolution_message_id(
            evolution_response
        )
    )


    recipient.status = (
        BulkCampaignRecipient.Status.SENT
    )

    recipient.provider_delivery_status = (
        BulkCampaignRecipient
        .ProviderDeliveryStatus.SENT
    )

    recipient.evolution_message_id = (
        evolution_message_id
    )

    recipient.sent_at = (
        timezone.now()
    )

    recipient.last_error = ""

    recipient.save(
        update_fields=[
            "status",
            "provider_delivery_status",
            "evolution_message_id",
            "sent_at",
            "last_error",
            "updated_at",
        ]
    )


    refresh_campaign_progress(
        recipient.campaign_id
    )


    return Response(
        {
            "success": True,

            "recipient_id": (
                recipient.pk
            ),

            "ghl_message_id": (
                recipient.ghl_message_id
            ),

            "evolution_message_id": (
                recipient.evolution_message_id
            ),
        }
    )
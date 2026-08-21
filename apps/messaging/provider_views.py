import json

from django.db import transaction
from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.ghl.models import GHLInstallation

from .ghl_provider_security import (
    verify_ghl_provider_signature,
)
from .models import (
    BulkCampaignRecipient,
    ProviderOutboundJob,
)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def ghl_provider_outbound(request):
    """
    Delivery URL du Custom Conversation Provider HighLevel.

    IMPORTANT:
    Cet endpoint ne contacte PAS Evolution API.

    Il vérifie la signature, enregistre le travail dans PostgreSQL,
    puis répond immédiatement 200 à HighLevel. Le bulk_worker effectue
    ensuite l'envoi réel vers Evolution API.

    Cela évite les timeouts / Broken pipe / retries HighLevel lorsque
    Evolution ou un envoi média prend plusieurs secondes.
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
                "message": "Signature HighLevel invalide.",
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

    message_type = str(
        payload.get("type")
        or ""
    ).strip()

    if message_type.upper() != "SMS":
        return Response(
            {
                "success": True,
                "ignored": True,
                "reason": "Type provider non supporté.",
            },
            status=status.HTTP_200_OK,
        )

    # Une fois la requête signée et reçue, on évite de provoquer
    # une tempête de retries HighLevel pour une erreur métier.
    if not (
        location_id
        and contact_id
        and ghl_message_id
        and message
    ):
        return Response(
            {
                "success": False,
                "accepted": False,
                "message": (
                    "Payload provider incomplet "
                    "(locationId/contactId/messageId/message)."
                ),
            },
            status=status.HTTP_200_OK,
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
                "accepted": False,
                "message": "Installation GHL introuvable.",
            },
            status=status.HTTP_200_OK,
        )

    # 1. Recherche par ID GHL si le worker a déjà pu le sauvegarder.
    recipient = (
        BulkCampaignRecipient.objects
        .select_related(
            "campaign",
            "campaign__installation",
        )
        .filter(
            campaign__installation=installation,
            ghl_message_id=ghl_message_id,
        )
        .first()
    )

    # 2. Le webhook peut arriver AVANT la réponse de
    # POST /conversations/messages. On retrouve alors le recipient
    # actuellement PROCESSING grâce au contact + message rendu.
    if recipient is None:
        recipient = (
            BulkCampaignRecipient.objects
            .select_related(
                "campaign",
                "campaign__installation",
            )
            .filter(
                campaign__installation=installation,
                ghl_contact_id=contact_id,
                status=(
                    BulkCampaignRecipient
                    .Status.PROCESSING
                ),
                rendered_message=message,
            )
            .order_by("-updated_at")
            .first()
        )

    if recipient is None:
        return Response(
            {
                "success": False,
                "accepted": False,
                "message": (
                    "Aucun destinataire bulk correspondant. "
                    "Webhook acquitté pour éviter les retries."
                ),
            },
            status=status.HTTP_200_OK,
        )

    # Idempotence: un messageId GHL ne crée qu'un seul travail.
    with transaction.atomic():
        job, created = (
            ProviderOutboundJob.objects
            .get_or_create(
                ghl_message_id=ghl_message_id,
                defaults={
                    "recipient": recipient,
                    "payload": payload,
                },
            )
        )

        if not created:
            # On conserve le dernier payload complet, mais on ne remet
            # jamais automatiquement un job SENT/PROCESSING à PENDING.
            changed = False

            if job.recipient_id != recipient.pk:
                job.recipient = recipient
                changed = True

            if job.payload != payload:
                job.payload = payload
                changed = True

            if changed:
                job.save(
                    update_fields=[
                        "recipient",
                        "payload",
                        "updated_at",
                    ]
                )

        update_fields = [
            "ghl_history_synced_at",
            "provider_delivery_status",
            "updated_at",
        ]

        if not recipient.ghl_message_id:
            recipient.ghl_message_id = ghl_message_id
            update_fields.append("ghl_message_id")

        recipient.ghl_history_synced_at = (
            recipient.ghl_history_synced_at
            or timezone.now()
        )

        if (
            recipient.provider_delivery_status
            == BulkCampaignRecipient
            .ProviderDeliveryStatus.PENDING
        ):
            recipient.provider_delivery_status = (
                BulkCampaignRecipient
                .ProviderDeliveryStatus.SUBMITTED
            )

        recipient.save(
            update_fields=update_fields
        )

    return Response(
        {
            "success": True,
            "accepted": True,
            "queued": True,
            "duplicate": not created,
            "job_id": job.pk,
            "recipient_id": recipient.pk,
            "ghl_message_id": ghl_message_id,
        },
        status=status.HTTP_200_OK,
    )

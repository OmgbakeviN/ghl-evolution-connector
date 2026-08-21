import time, mimetypes

from pathlib import Path
from urllib.parse import urlparse
from collections.abc import Iterable

from django.db import transaction
from django.utils import timezone

from apps.evolution.client import (
    EvolutionAPIError,
    EvolutionClient,
)
from apps.evolution.models import EvolutionInstance

from apps.ghl.client import (
    GHLAPIError,
    GHLClient,
)
from .models import (
    BulkCampaign,
    BulkCampaignRecipient,
    ProviderOutboundJob,
)

WHATSAPP_CHECK_BATCH_SIZE = 10
WHATSAPP_CHECK_DELAY_SECONDS = 2 

def chunked(
    items: list,
    size: int,
) -> Iterable[list]:

    for index in range(
        0,
        len(items),
        size,
    ):
        yield items[
            index:index + size
        ]

def normalize_check_result(
    result: dict,
) -> tuple[str, bool, str]:
    """
    Retourne :
        number
        exists
        jid
    """

    number = str(
        result.get("number")
        or result.get("phone")
        or ""
    ).strip()

    exists = bool(
        result.get("exists")
        if result.get("exists") is not None
        else result.get("isWhatsapp")
    )

    jid = str(
        result.get("jid")
        or result.get("remoteJid")
        or ""
    ).strip()

    # Certaines réponses peuvent fournir seulement le JID.
    if not number and jid:
        number = jid.split(
            "@",
            1,
        )[0]

    return (
        number,
        exists,
        jid,
    )

def validate_campaign_recipients(
    campaign: BulkCampaign | int,
) -> dict:

    campaign_id = (
        campaign.pk
        if isinstance(
            campaign,
            BulkCampaign,
        )
        else campaign
    )

    campaign = (
        BulkCampaign.objects
        .select_related(
            "installation"
        )
        .get(pk=campaign_id)
    )

    try:
        evolution_instance = (
            campaign
            .installation
            .evolution_instance
        )

    except EvolutionInstance.DoesNotExist:
        raise EvolutionAPIError(
            "Aucune instance Evolution n'est "
            "associée à cette campagne."
        )

    if (
        evolution_instance.status
        != EvolutionInstance.Status.OPEN
    ):
        raise EvolutionAPIError(
            "WhatsApp n'est pas connecté."
        )

    recipients = list(
        campaign.recipients
        .filter(
            status__in=[
                BulkCampaignRecipient
                .Status.PENDING,

                BulkCampaignRecipient
                .Status.FAILED,
            ]
        )
        .order_by("id")
    )

    if not recipients:

        return {
            "total": 0,
            "valid": 0,
            "invalid": 0,
            "errors": 0,
        }

    client = EvolutionClient()

    valid_count = 0
    invalid_count = 0
    error_count = 0

    for batch_number, batch in enumerate(
        chunked(
            recipients,
            WHATSAPP_CHECK_BATCH_SIZE,
        )
    ):

        # Passe les destinataires en VALIDATING.
        recipient_ids = [
            recipient.pk
            for recipient in batch
        ]

        BulkCampaignRecipient.objects.filter(
            pk__in=recipient_ids
        ).update(
            status=(
                BulkCampaignRecipient
                .Status.VALIDATING
            ),
            whatsapp_check_error="",
        )

        numbers = [
            recipient.normalized_phone
            for recipient in batch
        ]

        try:

            results = (
                client.check_whatsapp_numbers(
                    instance_name=(
                        evolution_instance
                        .instance_name
                    ),
                    numbers=numbers,
                )
            )

        except EvolutionAPIError as exc:

            error_count += len(batch)

            BulkCampaignRecipient.objects.filter(
                pk__in=recipient_ids
            ).update(
                status=(
                    BulkCampaignRecipient
                    .Status.FAILED
                ),
                whatsapp_check_error=str(
                    exc
                ),
                whatsapp_checked_at=(
                    timezone.now()
                ),
            )

            continue

        results_by_number = {}

        for result in results:

            if not isinstance(
                result,
                dict,
            ):
                continue

            number, exists, jid = (
                normalize_check_result(
                    result
                )
            )

            if number:
                results_by_number[
                    number
                ] = {
                    "exists": exists,
                    "jid": jid,
                }

        now = timezone.now()

        with transaction.atomic():

            for recipient in batch:

                result = (
                    results_by_number.get(
                        recipient
                        .normalized_phone
                    )
                )

                if result is None:

                    recipient.status = (
                        BulkCampaignRecipient
                        .Status.FAILED
                    )

                    recipient.is_on_whatsapp = (
                        None
                    )

                    recipient.whatsapp_check_error = (
                        "Evolution API n'a "
                        "retourné aucun résultat "
                        "pour ce numéro."
                    )

                    error_count += 1

                elif result["exists"]:

                    recipient.status = (
                        BulkCampaignRecipient
                        .Status.READY
                    )

                    recipient.is_on_whatsapp = (
                        True
                    )

                    recipient.whatsapp_jid = (
                        result["jid"]
                    )

                    recipient.whatsapp_check_error = (
                        ""
                    )

                    valid_count += 1

                else:

                    recipient.status = (
                        BulkCampaignRecipient
                        .Status.NOT_ON_WHATSAPP
                    )

                    recipient.is_on_whatsapp = (
                        False
                    )

                    recipient.whatsapp_jid = (
                        result["jid"]
                    )

                    recipient.whatsapp_check_error = (
                        ""
                    )

                    invalid_count += 1

                recipient.whatsapp_checked_at = (
                    now
                )

                recipient.save(
                    update_fields=[
                        "status",
                        "is_on_whatsapp",
                        "whatsapp_jid",
                        "whatsapp_checked_at",
                        "whatsapp_check_error",
                        "updated_at",
                    ]
                )

        # Pas de pause après le dernier batch.
        if (
            batch_number
            < (
                len(recipients) - 1
            )
            // WHATSAPP_CHECK_BATCH_SIZE
        ):
            time.sleep(
                WHATSAPP_CHECK_DELAY_SECONDS
            )

    campaign.validated_count = (
        valid_count
    )

    campaign.not_on_whatsapp_count = (
        invalid_count
    )

    campaign.validation_error_count = (
        error_count
    )

    campaign.save(
        update_fields=[
            "validated_count",
            "not_on_whatsapp_count",
            "validation_error_count",
            "updated_at",
        ]
    )

    return {
        "total": len(recipients),
        "valid": valid_count,
        "invalid": invalid_count,
        "errors": error_count,
    }

def render_campaign_message(
    template: str,
    recipient: BulkCampaignRecipient,
) -> str:

    message = str(
        template or ""
    )

    variables = {
        "{{firstName}}": recipient.first_name or "",
        "{{lastName}}": recipient.last_name or "",
        "{{email}}": recipient.email or "",
        "{{phone}}": recipient.phone or "",
    }

    for variable, value in variables.items():
        message = message.replace(
            variable,
            value,
        )

    return message.strip()

def extract_evolution_message_id(
    response,
) -> str:

    if isinstance(response, list):

        if not response:
            return ""

        response = response[0]

    if not isinstance(response, dict):
        return ""

    key = response.get("key")

    if isinstance(key, dict):

        message_id = key.get("id")

        if message_id:
            return str(message_id)

    data = response.get("data")

    if isinstance(data, dict):

        key = data.get("key")

        if isinstance(key, dict):

            message_id = key.get("id")

            if message_id:
                return str(message_id)

    return ""
    
def refresh_campaign_progress(
    campaign_id: int,
) -> BulkCampaign:

    campaign = BulkCampaign.objects.get(
        pk=campaign_id
    )

    recipients = campaign.recipients.all()

    sent_count = recipients.filter(
        status=BulkCampaignRecipient.Status.SENT
    ).count()

    failed_count = recipients.filter(
        status=BulkCampaignRecipient.Status.FAILED
    ).count()

    ready_count = recipients.filter(
        status=BulkCampaignRecipient.Status.READY
    ).count()

    processing_count = recipients.filter(
        status=BulkCampaignRecipient.Status.PROCESSING
    ).count()

    pending_count = recipients.filter(
        status=BulkCampaignRecipient.Status.PENDING
    ).count()

    validating_count = recipients.filter(
        status=BulkCampaignRecipient.Status.VALIDATING
    ).count()

    not_on_whatsapp_count = recipients.filter(
        status=(
            BulkCampaignRecipient
            .Status.NOT_ON_WHATSAPP
        )
    ).count()

    campaign.sent_count = sent_count
    campaign.failed_count = failed_count

    campaign.not_on_whatsapp_count = (
        not_on_whatsapp_count
    )

    remaining = (
        ready_count
        + processing_count
        + pending_count
        + validating_count
    )

    if remaining > 0:

        if campaign.status in [
            BulkCampaign.Status.QUEUED,
            BulkCampaign.Status.RUNNING,
        ]:
            campaign.status = (
                BulkCampaign.Status.RUNNING
            )

    else:

        if sent_count > 0 and failed_count > 0:

            campaign.status = (
                BulkCampaign.Status.PARTIAL
            )

        elif sent_count > 0:

            campaign.status = (
                BulkCampaign.Status.COMPLETED
            )

        elif failed_count > 0:

            campaign.status = (
                BulkCampaign.Status.FAILED
            )

        else:

            campaign.status = (
                BulkCampaign.Status.COMPLETED
            )

        if campaign.completed_at is None:
            campaign.completed_at = timezone.now()

    campaign.save(
        update_fields=[
            "status",
            "sent_count",
            "failed_count",
            "not_on_whatsapp_count",
            "completed_at",
            "updated_at",
        ]
    )

    return campaign

def claim_next_bulk_recipient():
    """
    Prend un seul recipient READY et le passe
    immédiatement en PROCESSING.

    PostgreSQL verrouille la ligne pendant
    cette transaction.
    """

    with transaction.atomic():

        recipient = (
            BulkCampaignRecipient.objects
            .select_for_update(
                skip_locked=True
            )
            .filter(
                campaign__status__in=[
                    BulkCampaign.Status.QUEUED,
                    BulkCampaign.Status.RUNNING,
                ],
                status=(
                    BulkCampaignRecipient
                    .Status.READY
                ),
                is_on_whatsapp=True,
            )
            .order_by(
                "campaign__created_at",
                "id",
            )
            .first()
        )

        if recipient is None:
            return None

        recipient.status = (
            BulkCampaignRecipient
            .Status.PROCESSING
        )

        recipient.attempts += 1

        recipient.last_error = ""

        recipient.save(
            update_fields=[
                "status",
                "attempts",
                "last_error",
                "updated_at",
            ]
        )

        BulkCampaign.objects.filter(
            pk=recipient.campaign_id,
            status=BulkCampaign.Status.QUEUED,
        ).update(
            status=BulkCampaign.Status.RUNNING,
            started_at=timezone.now(),
        )

        return recipient.pk

def process_bulk_recipient(
    recipient_id: int,
) -> dict:

    recipient = (
        BulkCampaignRecipient.objects
        .select_related(
            "campaign",
            "campaign__installation",
            "campaign__installation__evolution_instance",
        )
        .get(
            pk=recipient_id
        )
    )

    campaign = recipient.campaign

    if (
        recipient.status
        != BulkCampaignRecipient.Status.PROCESSING
    ):
        return {
            "status": "ignored",
            "recipient_id": recipient.pk,
        }

    if recipient.is_on_whatsapp is not True:

        recipient.status = (
            BulkCampaignRecipient.Status.SKIPPED
        )

        recipient.last_error = (
            "Le numéro n'est pas validé WhatsApp."
        )

        recipient.save(
            update_fields=[
                "status",
                "last_error",
                "updated_at",
            ]
        )

        refresh_campaign_progress(
            campaign.pk
        )

        return {
            "status": "skipped",
            "recipient_id": recipient.pk,
        }

    evolution_instance = (
        campaign
        .installation
        .evolution_instance
    )

    if (
        evolution_instance.status
        != EvolutionInstance.Status.OPEN
    ):
        #
        # On ne considère pas une déconnexion
        # WhatsApp comme un échec définitif.
        #

        recipient.status = (
            BulkCampaignRecipient.Status.READY
        )

        recipient.last_error = (
            "WhatsApp est actuellement déconnecté."
        )

        recipient.save(
            update_fields=[
                "status",
                "last_error",
                "updated_at",
            ]
        )

        return {
            "status": "waiting_connection",
            "recipient_id": recipient.pk,
        }

    rendered_message = (
        render_campaign_message(
            campaign.message_template,
            recipient,
        )
    )

    if not rendered_message:

        recipient.status = (
            BulkCampaignRecipient.Status.FAILED
        )

        recipient.last_error = (
            "Le message rendu est vide."
        )

        recipient.save(
            update_fields=[
                "status",
                "last_error",
                "updated_at",
            ]
        )

        refresh_campaign_progress(
            campaign.pk
        )

        return {
            "status": "failed",
            "recipient_id": recipient.pk,
        }

    recipient.rendered_message = (
        rendered_message
    )

    recipient.save(
        update_fields=[
            "rendered_message",
            "updated_at",
        ]
    )

    ghl_client = GHLClient(
        campaign.installation
    )

    try:

        attachments = [
            attachment.public_url()
            for attachment
            in campaign.attachments.all()
        ]

        response = (
            ghl_client.send_provider_message(
                contact_id=(
                    recipient.ghl_contact_id
                ),
                message=rendered_message,
                attachments=attachments,
            )
        )

    except GHLAPIError as exc:

        recipient.status = (
            BulkCampaignRecipient
            .Status.FAILED
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
            campaign.pk
        )

        return {
            "status": "failed",
            "recipient_id": recipient.pk,
            "error": str(exc),
        }


    ghl_message_id, ghl_conversation_id = (
        extract_ghl_message_ids(
            response
        )
    )


    #
    # IMPORTANT :
    # le webhook GHL peut arriver très rapidement,
    # éventuellement avant cette partie.
    #
    # On recharge donc le recipient avant
    # de modifier provider_delivery_status.
    #

    recipient.refresh_from_db()


    recipient.ghl_message_id = (
        ghl_message_id
        or recipient.ghl_message_id
    )

    recipient.ghl_conversation_id = (
        ghl_conversation_id
        or recipient.ghl_conversation_id
    )

    recipient.ghl_history_synced_at = (
        timezone.now()
    )


    if (
        recipient.provider_delivery_status
        == (
            BulkCampaignRecipient
            .ProviderDeliveryStatus.PENDING
        )
    ):
        recipient.provider_delivery_status = (
            BulkCampaignRecipient
            .ProviderDeliveryStatus.SUBMITTED
        )


    recipient.save(
        update_fields=[
            "ghl_message_id",
            "ghl_conversation_id",
            "ghl_history_synced_at",
            "provider_delivery_status",
            "updated_at",
        ]
    )

    return {
        "status": "submitted_to_ghl",
        "recipient_id": recipient.pk,
        "ghl_message_id": (
            recipient.ghl_message_id
        ),
        "ghl_conversation_id": (
            recipient.ghl_conversation_id
        ),
    }

def extract_ghl_message_ids(
        response: dict,
    ) -> tuple[str, str]:

        if not isinstance(response, dict):
            return "", ""

        message_id = str(
            response.get("messageId")
            or ""
        ).strip()

        conversation_id = str(
            response.get("conversationId")
            or ""
        ).strip()

        if (
            not message_id
            and isinstance(
                response.get("data"),
                dict,
            )
        ):
            data = response["data"]

            message_id = str(
                data.get("messageId")
                or ""
            ).strip()

            conversation_id = str(
                data.get("conversationId")
                or ""
            ).strip()

        return (
            message_id,
            conversation_id,
        )

def detect_evolution_media_type(
    url: str,
):

    path = urlparse(url).path

    mime_type, _ = (
        mimetypes.guess_type(
            path
        )
    )

    mime_type = mime_type or ""

    if mime_type.startswith(
        "image/"
    ):
        return (
            "image",
            mime_type,
        )

    return (
        "document",
        mime_type,
    )


def media_filename(
    url: str,
):

    return Path(
        urlparse(url).path
    ).name



def claim_next_provider_outbound_job():
    """
    Réserve un Delivery Job HighLevel depuis PostgreSQL.
    """

    with transaction.atomic():
        job = (
            ProviderOutboundJob.objects
            .select_for_update(skip_locked=True)
            .filter(
                status=ProviderOutboundJob.Status.PENDING
            )
            .order_by("created_at", "id")
            .first()
        )

        if job is None:
            return None

        job.status = ProviderOutboundJob.Status.PROCESSING
        job.attempts += 1
        job.last_error = ""

        job.save(
            update_fields=[
                "status",
                "attempts",
                "last_error",
                "updated_at",
            ]
        )

        return job.pk


def process_provider_outbound_job(
    job_id: int,
) -> dict:
    """
    Effectue le vrai transport WhatsApp après que HighLevel a déjà
    reçu un HTTP 200 de la Delivery URL.
    """

    job = (
        ProviderOutboundJob.objects
        .select_related(
            "recipient",
            "recipient__campaign",
            "recipient__campaign__installation",
            "recipient__campaign__installation__evolution_instance",
        )
        .get(pk=job_id)
    )

    if job.status != ProviderOutboundJob.Status.PROCESSING:
        return {
            "status": "ignored",
            "job_id": job.pk,
        }

    recipient = job.recipient
    campaign = recipient.campaign
    payload = job.payload or {}

    # Protection idempotente.
    if recipient.status == BulkCampaignRecipient.Status.SENT:
        job.status = ProviderOutboundJob.Status.SENT
        job.processed_at = timezone.now()
        job.save(
            update_fields=[
                "status",
                "processed_at",
                "updated_at",
            ]
        )
        return {
            "status": "duplicate",
            "job_id": job.pk,
            "recipient_id": recipient.pk,
        }

    try:
        evolution_instance = (
            campaign.installation.evolution_instance
        )
    except EvolutionInstance.DoesNotExist:
        error_message = (
            "Aucune instance Evolution associée au sous-compte."
        )
        return _fail_provider_outbound_job(
            job,
            recipient,
            error_message,
        )

    if evolution_instance.status != EvolutionInstance.Status.OPEN:
        error_message = "WhatsApp est déconnecté."
        return _fail_provider_outbound_job(
            job,
            recipient,
            error_message,
        )

    message = str(
        payload.get("message")
        or recipient.rendered_message
        or ""
    ).strip()

    attachments = payload.get("attachments") or []

    if not isinstance(attachments, list):
        attachments = []

    if not message:
        return _fail_provider_outbound_job(
            job,
            recipient,
            "Le message provider est vide.",
        )

    evolution_client = EvolutionClient()
    evolution_message_ids = []

    try:
        if attachments:
            for index, media_url in enumerate(attachments):
                media_url = str(media_url or "").strip()

                if not media_url:
                    continue

                media_type, mime_type = (
                    detect_evolution_media_type(
                        media_url
                    )
                )

                response = (
                    evolution_client.send_media(
                        instance_name=(
                            evolution_instance.instance_name
                        ),
                        number=recipient.normalized_phone,
                        media_type=media_type,
                        media=media_url,
                        caption=(
                            message
                            if index == 0
                            else ""
                        ),
                        file_name=(
                            media_filename(media_url)
                        ),
                        mimetype=mime_type,
                        delay_ms=1000,
                    )
                )

                message_id = (
                    extract_evolution_message_id(
                        response
                    )
                )

                if message_id:
                    evolution_message_ids.append(
                        message_id
                    )
        else:
            response = (
                evolution_client.send_text(
                    instance_name=(
                        evolution_instance.instance_name
                    ),
                    number=recipient.normalized_phone,
                    text=message,
                    delay_ms=1000,
                )
            )

            message_id = (
                extract_evolution_message_id(
                    response
                )
            )

            if message_id:
                evolution_message_ids.append(
                    message_id
                )

    except EvolutionAPIError as exc:
        recipient.evolution_message_ids = (
            evolution_message_ids
        )
        recipient.save(
            update_fields=[
                "evolution_message_ids",
                "updated_at",
            ]
        )

        return _fail_provider_outbound_job(
            job,
            recipient,
            str(exc),
        )

    now = timezone.now()

    with transaction.atomic():
        job = (
            ProviderOutboundJob.objects
            .select_for_update()
            .get(pk=job.pk)
        )

        recipient = (
            BulkCampaignRecipient.objects
            .select_for_update()
            .get(pk=recipient.pk)
        )

        job.status = ProviderOutboundJob.Status.SENT
        job.last_error = ""
        job.processed_at = now
        job.save(
            update_fields=[
                "status",
                "last_error",
                "processed_at",
                "updated_at",
            ]
        )

        recipient.status = (
            BulkCampaignRecipient.Status.SENT
        )
        recipient.provider_delivery_status = (
            BulkCampaignRecipient
            .ProviderDeliveryStatus.SENT
        )
        recipient.evolution_message_ids = (
            evolution_message_ids
        )
        recipient.evolution_message_id = (
            evolution_message_ids[0]
            if evolution_message_ids
            else ""
        )
        recipient.sent_at = now
        recipient.last_error = ""

        recipient.save(
            update_fields=[
                "status",
                "provider_delivery_status",
                "evolution_message_ids",
                "evolution_message_id",
                "sent_at",
                "last_error",
                "updated_at",
            ]
        )

    refresh_campaign_progress(
        campaign.pk
    )

    return {
        "status": "sent",
        "job_id": job.pk,
        "recipient_id": recipient.pk,
        "evolution_message_ids": evolution_message_ids,
    }


def _fail_provider_outbound_job(
    job: ProviderOutboundJob,
    recipient: BulkCampaignRecipient,
    error_message: str,
) -> dict:

    now = timezone.now()

    ProviderOutboundJob.objects.filter(
        pk=job.pk
    ).update(
        status=ProviderOutboundJob.Status.FAILED,
        last_error=error_message,
        processed_at=now,
    )

    BulkCampaignRecipient.objects.filter(
        pk=recipient.pk
    ).update(
        status=BulkCampaignRecipient.Status.FAILED,
        provider_delivery_status=(
            BulkCampaignRecipient
            .ProviderDeliveryStatus.FAILED
        ),
        last_error=error_message,
    )

    refresh_campaign_progress(
        recipient.campaign_id
    )

    return {
        "status": "failed",
        "job_id": job.pk,
        "recipient_id": recipient.pk,
        "error": error_message,
    }

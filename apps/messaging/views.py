from django.db import transaction

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
)

from .services import (
    validate_campaign_recipients,
)

from apps.ghl.client import (
    GHLAPIError,
    GHLClient,
)
from apps.ghl.embedded_tokens import (
    GHLEmbeddedTokenError,
    GHLEmbeddedTokenExpired,
    decode_embedded_token,
)
from apps.ghl.models import GHLInstallation

from .models import (
    BulkCampaign,
    BulkCampaignRecipient,
)
from .utils import normalize_phone


def extract_bearer_token(request) -> str:
    authorization = request.headers.get(
        "Authorization",
        "",
    ).strip()

    scheme, separator, token = authorization.partition(" ")

    if (
        separator != " "
        or scheme.lower() != "bearer"
        or not token.strip()
    ):
        return ""

    return token.strip()


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def create_bulk_campaign_draft(request):

    token = extract_bearer_token(request)

    if not token:
        return Response(
            {
                "success": False,
                "message": "Token Custom Page absent.",
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        context = decode_embedded_token(token)

    except GHLEmbeddedTokenExpired as exc:
        return Response(
            {
                "success": False,
                "code": "embedded_token_expired",
                "message": str(exc),
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    except GHLEmbeddedTokenError as exc:
        return Response(
            {
                "success": False,
                "message": str(exc),
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    location_id = context["location_id"]

    installation = GHLInstallation.objects.filter(
        location_id=location_id,
        is_active=True,
    ).first()

    if installation is None:
        return Response(
            {
                "success": False,
                "message": "Installation HighLevel introuvable.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    name = str(
        request.data.get("name") or ""
    ).strip()

    message_template = str(
        request.data.get("message") or ""
    ).strip()

    contact_ids = request.data.get(
        "contact_ids",
        [],
    )

    confirmed_opt_in = bool(
        request.data.get("confirmed_opt_in")
    )

    if not name:
        return Response(
            {
                "success": False,
                "message": "Le nom de la campagne est obligatoire.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not message_template:
        return Response(
            {
                "success": False,
                "message": "Le message est obligatoire.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if len(message_template) > 4000:
        return Response(
            {
                "success": False,
                "message": "Le message est trop long.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not isinstance(contact_ids, list):
        return Response(
            {
                "success": False,
                "message": "contact_ids doit être une liste.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Supprime les doublons.
    contact_ids = list(
        dict.fromkeys(
            str(contact_id).strip()
            for contact_id in contact_ids
            if str(contact_id).strip()
        )
    )

    if not contact_ids:
        return Response(
            {
                "success": False,
                "message": "Sélectionnez au moins un contact.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Limite temporaire pendant que nous n'avons pas
    # encore Celery + Redis.
    if len(contact_ids) > 100:
        return Response(
            {
                "success": False,
                "message": (
                    "La version actuelle accepte "
                    "au maximum 100 contacts par campagne."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not confirmed_opt_in:
        return Response(
            {
                "success": False,
                "message": (
                    "Confirmez que les destinataires "
                    "sont autorisés à recevoir ces messages."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    ghl_client = GHLClient(
        installation
    )

    valid_contacts = []
    invalid_contacts = []

    for contact_id in contact_ids:

        try:
            contact = ghl_client.get_contact(
                contact_id
            )

        except GHLAPIError as exc:
            invalid_contacts.append(
                {
                    "id": contact_id,
                    "reason": str(exc),
                }
            )
            continue

        phone = str(
            contact.get("phone") or ""
        ).strip()

        normalized_phone = normalize_phone(
            phone
        )

        if not normalized_phone:
            invalid_contacts.append(
                {
                    "id": contact_id,
                    "reason": "Aucun numéro de téléphone.",
                }
            )
            continue

        valid_contacts.append(
            {
                "id": contact_id,
                "first_name": str(
                    contact.get("firstName") or ""
                ),
                "last_name": str(
                    contact.get("lastName") or ""
                ),
                "email": str(
                    contact.get("email") or ""
                ),
                "phone": phone,
                "normalized_phone": normalized_phone,
            }
        )

    if not valid_contacts:
        return Response(
            {
                "success": False,
                "message": (
                    "Aucun destinataire valide "
                    "n'a été trouvé."
                ),
                "invalid_contacts": invalid_contacts,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    with transaction.atomic():

        campaign = BulkCampaign.objects.create(
            installation=installation,
            name=name[:255],
            message_template=message_template,
            created_by_highlevel_user_id=context[
                "user_id"
            ],
            total_contacts=len(valid_contacts),
            skipped_count=len(invalid_contacts),
        )

        recipients = [
            BulkCampaignRecipient(
                campaign=campaign,
                ghl_contact_id=contact["id"],
                first_name=contact["first_name"],
                last_name=contact["last_name"],
                email=contact["email"],
                phone=contact["phone"],
                normalized_phone=contact[
                    "normalized_phone"
                ],
            )
            for contact in valid_contacts
        ]

        BulkCampaignRecipient.objects.bulk_create(
            recipients
        )

    return Response(
        {
            "success": True,
            "message": "Brouillon de campagne créé.",
            "campaign": {
                "id": campaign.pk,
                "name": campaign.name,
                "status": campaign.status,
                "total_contacts": campaign.total_contacts,
                "skipped_count": campaign.skipped_count,
            },
            "invalid_contacts": invalid_contacts,
        },
        status=status.HTTP_201_CREATED,
    )

@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def validate_bulk_campaign(
    request,
    campaign_id: int,
):

    token = extract_bearer_token(
        request
    )

    if not token:

        return Response(
            {
                "success": False,
                "message": (
                    "Token Custom Page absent."
                ),
            },
            status=401,
        )

    try:

        context = decode_embedded_token(
            token
        )

    except (
        GHLEmbeddedTokenExpired,
        GHLEmbeddedTokenError,
    ) as exc:

        return Response(
            {
                "success": False,
                "message": str(exc),
            },
            status=401,
        )

    campaign = (
        BulkCampaign.objects
        .select_related(
            "installation"
        )
        .filter(
            pk=campaign_id,
            installation__location_id=(
                context["location_id"]
            ),
        )
        .first()
    )

    if campaign is None:

        return Response(
            {
                "success": False,
                "message": (
                    "Campagne introuvable."
                ),
            },
            status=404,
        )

    if campaign.status != (
        BulkCampaign.Status.DRAFT
    ):

        return Response(
            {
                "success": False,
                "message": (
                    "Cette campagne ne peut "
                    "plus être validée."
                ),
            },
            status=400,
        )

    try:

        result = (
            validate_campaign_recipients(
                campaign
            )
        )

    except EvolutionAPIError as exc:

        return Response(
            {
                "success": False,
                "message": str(exc),
            },
            status=502,
        )

    return Response(
        {
            "success": True,
            "message": (
                "Validation WhatsApp terminée."
            ),
            "validation": result,
        }
    )

@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def start_bulk_campaign(
    request,
    campaign_id: int,
):

    token = extract_bearer_token(
        request
    )

    if not token:

        return Response(
            {
                "success": False,
                "message": (
                    "Token Custom Page absent."
                ),
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    try:

        context = decode_embedded_token(
            token
        )

    except (
        GHLEmbeddedTokenExpired,
        GHLEmbeddedTokenError,
    ) as exc:

        return Response(
            {
                "success": False,
                "message": str(exc),
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    with transaction.atomic():

        campaign = (
            BulkCampaign.objects
            .select_for_update()
            .filter(
                pk=campaign_id,
                installation__location_id=(
                    context["location_id"]
                ),
            )
            .first()
        )

        if campaign is None:

            return Response(
                {
                    "success": False,
                    "message": (
                        "Campagne introuvable."
                    ),
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if (
            campaign.status
            != BulkCampaign.Status.DRAFT
        ):

            return Response(
                {
                    "success": False,
                    "message": (
                        "Cette campagne a déjà "
                        "été démarrée."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        unchecked_count = (
            campaign.recipients
            .filter(
                status__in=[
                    BulkCampaignRecipient
                    .Status.PENDING,

                    BulkCampaignRecipient
                    .Status.VALIDATING,
                ]
            )
            .count()
        )

        if unchecked_count > 0:

            return Response(
                {
                    "success": False,
                    "message": (
                        f"{unchecked_count} contact(s) "
                        "n'ont pas encore été "
                        "vérifiés sur WhatsApp."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        ready_count = (
            campaign.recipients
            .filter(
                status=(
                    BulkCampaignRecipient
                    .Status.READY
                ),
                is_on_whatsapp=True,
            )
            .count()
        )

        if ready_count == 0:

            return Response(
                {
                    "success": False,
                    "message": (
                        "Aucun numéro WhatsApp valide "
                        "dans cette campagne."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        campaign.status = (
            BulkCampaign.Status.QUEUED
        )

        campaign.started_at = None
        campaign.completed_at = None

        campaign.save(
            update_fields=[
                "status",
                "started_at",
                "completed_at",
                "updated_at",
            ]
        )

    return Response(
        {
            "success": True,
            "message": (
                "Campagne ajoutée à la "
                "file d'envoi."
            ),
            "campaign": {
                "id": campaign.pk,
                "status": campaign.status,
                "ready_contacts": ready_count,
            },
        },
        status=status.HTTP_202_ACCEPTED,
    )

@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def bulk_campaign_status(
    request,
    campaign_id: int,
):

    token = extract_bearer_token(
        request
    )

    if not token:

        return Response(
            {
                "success": False,
                "message": "Token absent.",
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    try:

        context = decode_embedded_token(
            token
        )

    except (
        GHLEmbeddedTokenExpired,
        GHLEmbeddedTokenError,
    ) as exc:

        return Response(
            {
                "success": False,
                "message": str(exc),
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    campaign = (
        BulkCampaign.objects
        .filter(
            pk=campaign_id,
            installation__location_id=(
                context["location_id"]
            ),
        )
        .first()
    )

    if campaign is None:

        return Response(
            {
                "success": False,
                "message": (
                    "Campagne introuvable."
                ),
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    recipients = (
        campaign.recipients.all()
    )

    counts = {
        "pending": recipients.filter(
            status=(
                BulkCampaignRecipient
                .Status.PENDING
            )
        ).count(),

        "ready": recipients.filter(
            status=(
                BulkCampaignRecipient
                .Status.READY
            )
        ).count(),

        "processing": recipients.filter(
            status=(
                BulkCampaignRecipient
                .Status.PROCESSING
            )
        ).count(),

        "sent": recipients.filter(
            status=(
                BulkCampaignRecipient
                .Status.SENT
            )
        ).count(),

        "failed": recipients.filter(
            status=(
                BulkCampaignRecipient
                .Status.FAILED
            )
        ).count(),

        "not_on_whatsapp": (
            recipients.filter(
                status=(
                    BulkCampaignRecipient
                    .Status.NOT_ON_WHATSAPP
                )
            ).count()
        ),
    }

    return Response(
        {
            "success": True,

            "campaign": {
                "id": campaign.pk,
                "name": campaign.name,
                "status": campaign.status,
                "total_contacts": (
                    campaign.total_contacts
                ),
                "sent_count": (
                    campaign.sent_count
                ),
                "failed_count": (
                    campaign.failed_count
                ),
                "not_on_whatsapp_count": (
                    campaign
                    .not_on_whatsapp_count
                ),
                "started_at": (
                    campaign.started_at
                ),
                "completed_at": (
                    campaign.completed_at
                ),
            },

            "recipients": counts,
        }
    )

@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def list_bulk_campaigns(request):

    token = extract_bearer_token(
        request
    )

    if not token:
        return Response(
            {
                "success": False,
                "message": "Token absent.",
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        context = decode_embedded_token(
            token
        )

    except (
        GHLEmbeddedTokenExpired,
        GHLEmbeddedTokenError,
    ) as exc:

        return Response(
            {
                "success": False,
                "message": str(exc),
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    campaigns = (
        BulkCampaign.objects
        .filter(
            installation__location_id=(
                context["location_id"]
            )
        )
        .order_by("-created_at")[:100]
    )

    data = []

    for campaign in campaigns:

        data.append(
            {
                "id": campaign.pk,
                "name": campaign.name,
                "status": campaign.status,

                "total_contacts": (
                    campaign.total_contacts
                ),

                "validated_count": (
                    campaign.validated_count
                ),

                "sent_count": (
                    campaign.sent_count
                ),

                "failed_count": (
                    campaign.failed_count
                ),

                "skipped_count": (
                    campaign.skipped_count
                ),

                "not_on_whatsapp_count": (
                    campaign.not_on_whatsapp_count
                ),

                "validation_error_count": (
                    campaign.validation_error_count
                ),

                "created_at": (
                    campaign.created_at
                ),

                "started_at": (
                    campaign.started_at
                ),

                "completed_at": (
                    campaign.completed_at
                ),
            }
        )

    return Response(
        {
            "success": True,
            "campaigns": data,
        }
    )
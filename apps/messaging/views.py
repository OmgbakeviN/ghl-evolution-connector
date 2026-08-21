import json 

from django.db import transaction

from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .attachments import (
    MAX_CAMPAIGN_ATTACHMENTS,
    validate_campaign_file,
)

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
    CampaignAttachment,
)
from .utils import normalize_phone

def parse_contact_ids(value):

    if isinstance(value, list):
        return value

    if isinstance(value, str):

        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []

        if isinstance(parsed, list):
            return parsed

    return []


def parse_boolean(value):

    if isinstance(value, bool):
        return value

    return str(
        value or ""
    ).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

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

    contact_ids = parse_contact_ids(
        request.data.get(
            "contact_ids", 
            [],
        )
    )

    confirmed_opt_in = parse_boolean(
        request.data.get(
            "confirmed_opt_in",
        )
    )

    uploaded_files = (
        request.FILES.getlist(
            "attachments"
        )
    )

    if (
        len(uploaded_files)
        > MAX_CAMPAIGN_ATTACHMENTS
    ):
        return Response(
            {
                "success": False,
                "message": (
                    "Maximum 5 fichiers "
                    "par campagne."
                ),
            },
            status=400,
        )


    validated_files = []

    for uploaded_file in uploaded_files:

        try:
            kind = validate_campaign_file(
                uploaded_file
            )

        except ValueError as exc:

            return Response(
                {
                    "success": False,
                    "message": str(exc),
                },
                status=400,
            )

        validated_files.append(
            (
                uploaded_file,
                kind,
            )
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

        for uploaded_file, kind in validated_files:

            CampaignAttachment.objects.create(
                campaign=campaign,
                file=uploaded_file,
                original_name=(
                    uploaded_file.name
                ),
                mime_type=(
                    uploaded_file.content_type
                    or ""
                ),
                size=uploaded_file.size,
                kind=kind,
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

@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def relaunch_bulk_campaign(
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


    source = (
        BulkCampaign.objects
        .prefetch_related(
            "recipients",
            "attachments",
        )
        .filter(
            pk=campaign_id,
            installation__location_id=(
                context["location_id"]
            ),
        )
        .first()
    )


    if source is None:

        return Response(
            {
                "success": False,
                "message": (
                    "Campagne introuvable."
                ),
            },
            status=404,
        )


    if source.status in {
        BulkCampaign.Status.QUEUED,
        BulkCampaign.Status.RUNNING,
    }:

        return Response(
            {
                "success": False,
                "message": (
                    "Une campagne active "
                    "ne peut pas être relancée."
                ),
            },
            status=400,
        )


    mode = str(
        request.data.get("mode")
        or "same"
    ).lower()


    if mode not in {
        "same",
        "custom",
    }:

        return Response(
            {
                "success": False,
                "message": (
                    "Mode de relance invalide."
                ),
            },
            status=400,
        )


    if mode == "same":

        message = (
            source.message_template
        )

    else:

        message = str(
            request.data.get("message")
            or ""
        ).strip()

        if not message:

            return Response(
                {
                    "success": False,
                    "message": (
                        "Le nouveau message "
                        "est obligatoire."
                    ),
                },
                status=400,
            )


    name = str(
        request.data.get("name")
        or (
            f"{source.name} "
            f"- Relance"
        )
    ).strip()


    copy_attachments = parse_boolean(
        request.data.get(
            "copy_attachments",
            True,
        )
    )


    with transaction.atomic():

        relaunch_number = (
            source.relaunches.count()
            + 1
        )

        new_campaign = (
            BulkCampaign.objects.create(
                installation=(
                    source.installation
                ),

                source_campaign=source,

                relaunch_number=(
                    relaunch_number
                ),

                name=name[:255],

                message_template=message,

                status=(
                    BulkCampaign.Status.DRAFT
                ),

                created_by_highlevel_user_id=(
                    context["user_id"]
                ),

                total_contacts=(
                    source.recipients.count()
                ),
            )
        )


        new_recipients = []

        for old in source.recipients.all():

            new_recipients.append(
                BulkCampaignRecipient(
                    campaign=new_campaign,

                    ghl_contact_id=(
                        old.ghl_contact_id
                    ),

                    first_name=(
                        old.first_name
                    ),

                    last_name=(
                        old.last_name
                    ),

                    email=old.email,

                    phone=old.phone,

                    normalized_phone=(
                        old.normalized_phone
                    ),

                    status=(
                        BulkCampaignRecipient
                        .Status.PENDING
                    ),

                    is_on_whatsapp=None,
                )
            )


        BulkCampaignRecipient.objects.bulk_create(
            new_recipients
        )


        if copy_attachments:

            for old_attachment in (
                source.attachments.all()
            ):

                CampaignAttachment.objects.create(
                    campaign=new_campaign,

                    file=(
                        old_attachment.file.name
                    ),

                    original_name=(
                        old_attachment
                        .original_name
                    ),

                    mime_type=(
                        old_attachment
                        .mime_type
                    ),

                    size=(
                        old_attachment.size
                    ),

                    kind=(
                        old_attachment.kind
                    ),
                )


    return Response(
        {
            "success": True,

            "message": (
                "Nouvelle campagne "
                "de relance créée."
            ),

            "campaign": {
                "id": new_campaign.pk,

                "name": (
                    new_campaign.name
                ),

                "status": (
                    new_campaign.status
                ),

                "source_campaign_id": (
                    source.pk
                ),

                "relaunch_number": (
                    new_campaign
                    .relaunch_number
                ),

                "total_contacts": (
                    new_campaign
                    .total_contacts
                ),
            },
        },
        status=201,
    )
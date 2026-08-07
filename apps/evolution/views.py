from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_safe
from django.views.decorators.clickjacking import xframe_options_exempt

from apps.ghl.models import GHLInstallation
from apps.ghl.embedded_tokens import (
    GHLEmbeddedTokenError,
    GHLEmbeddedTokenExpired,
    decode_embedded_token
)

from .client import EvolutionAPIError, EvolutionClient
from .models import EvolutionInstance
from .services import (
    normalize_instance_status,
    provision_evolution_instance,
)


def extract_connection_state(payload: dict[str, Any]) -> str:
    """
    Extrait le statut malgré les petites différences possibles
    entre les versions d'Evolution API.
    """

    instance_data = payload.get("instance")

    if isinstance(instance_data, dict):
        state = (
            instance_data.get("state")
            or instance_data.get("status")
            or instance_data.get("connectionStatus")
        )

        if state:
            return str(state).lower()

    state = (
        payload.get("state")
        or payload.get("status")
        or payload.get("connectionStatus")
    )

    return str(state or "created").lower()


def normalize_qr_source(base64_value: str | None) -> str:
    """
    Transforme une chaîne Base64 en URL utilisable par une balise <img>.
    """

    if not base64_value:
        return ""

    base64_value = base64_value.strip()

    if base64_value.startswith("data:image/"):
        return base64_value

    return f"data:image/png;base64,{base64_value}"


def get_instance_snapshot(
    evolution_instance: EvolutionInstance,
) -> dict[str, Any]:
    """
    Récupère l'état actuel de l'instance et éventuellement son QR Code.
    """

    client = EvolutionClient()

    connection_payload = client.get_connection_state(
        evolution_instance.instance_name
    )

    raw_state = extract_connection_state(connection_payload)
    status = normalize_instance_status(raw_state)

    qr_source = ""
    qr_count = None
    pairing_code = None

    if status != EvolutionInstance.Status.OPEN:
        qr_payload = client.connect_instance(
            evolution_instance.instance_name
        )

        qr_source = normalize_qr_source(
            qr_payload.get("base64")
        )

        qr_count = qr_payload.get("count")
        pairing_code = qr_payload.get("pairingCode")

        if qr_source and status in {
            EvolutionInstance.Status.CREATED,
            EvolutionInstance.Status.CLOSE,
        }:
            status = EvolutionInstance.Status.CONNECTING

    fields_to_update = []

    if evolution_instance.status != status:
        evolution_instance.status = status
        fields_to_update.append("status")

    if (
        status == EvolutionInstance.Status.OPEN
        and evolution_instance.connected_at is None
    ):
        evolution_instance.connected_at = timezone.now()
        fields_to_update.append("connected_at")

    evolution_instance.last_synced_at = timezone.now()
    evolution_instance.last_error = ""

    fields_to_update.extend(
        [
            "last_synced_at",
            "last_error",
            "updated_at",
        ]
    )

    evolution_instance.save(
        update_fields=list(dict.fromkeys(fields_to_update))
    )

    return {
        "status": status,
        "is_connected": status == EvolutionInstance.Status.OPEN,
        "qr_source": qr_source,
        "qr_count": qr_count,
        "pairing_code": pairing_code,
        "phone_number": evolution_instance.phone_number,
        "profile_name": evolution_instance.profile_name,
        "last_synced_at": evolution_instance.last_synced_at,
    }


@require_GET
@staff_member_required
def whatsapp_dashboard(request, location_id: str):
    """
    Page HTML affichant l'état de l'instance et le QR Code.

    Protection temporaire :
    seuls les administrateurs Django peuvent ouvrir cette page.
    """

    installation = get_object_or_404(
        GHLInstallation,
        location_id=location_id,
        is_active=True,
    )

    evolution_instance, _ = provision_evolution_instance(
        installation
    )

    error_message = ""

    try:
        snapshot = get_instance_snapshot(evolution_instance)
    except EvolutionAPIError as exc:
        snapshot = {
            "status": EvolutionInstance.Status.ERROR,
            "is_connected": False,
            "qr_source": "",
            "qr_count": None,
            "pairing_code": None,
            "phone_number": evolution_instance.phone_number,
            "profile_name": evolution_instance.profile_name,
            "last_synced_at": evolution_instance.last_synced_at,
        }

        error_message = str(exc)

        if exc.details:
            error_message += f" — {exc.details}"

        evolution_instance.status = EvolutionInstance.Status.ERROR
        evolution_instance.last_error = error_message

        evolution_instance.save(
            update_fields=[
                "status",
                "last_error",
                "updated_at",
            ]
        )

    return render(
        request,
        "evolution/dashboard.html",
        {
            "installation": installation,
            "evolution_instance": evolution_instance,
            "snapshot": snapshot,
            "error_message": error_message,
            "status_url": reverse(
                "evolution:instance-status",
                kwargs={"location_id": installation.location_id},
            ),
        },
    )


@require_GET
@staff_member_required
def instance_status(request, location_id: str):
    """
    Endpoint JSON utilisé par JavaScript pour actualiser la page.
    """

    installation = get_object_or_404(
        GHLInstallation,
        location_id=location_id,
        is_active=True,
    )

    evolution_instance, _ = provision_evolution_instance(
        installation
    )

    try:
        snapshot = get_instance_snapshot(evolution_instance)
    except EvolutionAPIError as exc:
        error_message = str(exc)

        if exc.details:
            error_message += f" — {exc.details}"

        evolution_instance.status = EvolutionInstance.Status.ERROR
        evolution_instance.last_error = error_message

        evolution_instance.save(
            update_fields=[
                "status",
                "last_error",
                "updated_at",
            ]
        )

        return JsonResponse(
            {
                "success": False,
                "status": "error",
                "message": error_message,
            },
            status=502,
        )

    last_synced_at = snapshot.get("last_synced_at")

    return JsonResponse(
        {
            "success": True,
            "status": snapshot["status"],
            "is_connected": snapshot["is_connected"],
            "qr_source": snapshot["qr_source"],
            "qr_count": snapshot["qr_count"],
            "pairing_code": snapshot["pairing_code"],
            "phone_number": snapshot["phone_number"],
            "profile_name": snapshot["profile_name"],
            "last_synced_at": (
                last_synced_at.isoformat()
                if last_synced_at
                else None
            ),
        }
    )

@xframe_options_exempt
@require_safe
def embedded_dashboard(request):
    """
    Page temporaire utilisée pour vérifier l'intégration
    de la Custom Page HighLevel.
    """

    return render(
        request,
        "evolution/embedded.html",
    )

def extract_bearer_token(request) -> str:
    """
    Extrait le jeton depuis :
    Authorization: Bearer <token>
    """

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


@require_GET
def embedded_instance_status(request):
    """
    Retourne le statut WhatsApp de la Location contenue
    dans le jeton Django signé.

    Aucun location_id n'est accepté dans l'URL.
    """

    token = extract_bearer_token(request)

    if not token:
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Le jeton d'authentification "
                    "de la Custom Page est absent."
                ),
            },
            status=401,
        )

    try:
        token_context = decode_embedded_token(token)

    except GHLEmbeddedTokenExpired as exc:
        return JsonResponse(
            {
                "success": False,
                "code": "embedded_token_expired",
                "message": str(exc),
            },
            status=401,
        )

    except GHLEmbeddedTokenError as exc:
        return JsonResponse(
            {
                "success": False,
                "code": "invalid_embedded_token",
                "message": str(exc),
            },
            status=401,
        )

    location_id = token_context["location_id"]

    installation = GHLInstallation.objects.filter(
        location_id=location_id,
        is_active=True,
    ).first()

    if installation is None:
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Aucune installation HighLevel active "
                    "n'existe pour ce sous-compte."
                ),
            },
            status=404,
        )

    try:
        evolution_instance, _ = (
            provision_evolution_instance(installation)
        )

        snapshot = get_instance_snapshot(
            evolution_instance
        )

    except EvolutionAPIError as exc:
        error_message = str(exc)

        if exc.details:
            error_message += f" — {exc.details}"

        return JsonResponse(
            {
                "success": False,
                "status": "error",
                "message": error_message,
            },
            status=502,
        )

    last_synced_at = snapshot.get(
        "last_synced_at"
    )

    response = JsonResponse(
        {
            "success": True,
            "status": snapshot["status"],
            "is_connected": snapshot["is_connected"],
            "qr_source": snapshot["qr_source"],
            "qr_count": snapshot["qr_count"],
            "pairing_code": snapshot["pairing_code"],
            "phone_number": snapshot["phone_number"],
            "profile_name": snapshot["profile_name"],
            "last_synced_at": (
                last_synced_at.isoformat()
                if last_synced_at
                else None
            ),
            "instance": {
                "name": evolution_instance.instance_name,
                "integration": (
                    evolution_instance.integration
                ),
            },
            "location": {
                "id": installation.location_id,
            },
            "user": {
                "id": token_context["user_id"],
                "role": token_context["role"],
            },
        }
    )

    response["Cache-Control"] = (
        "no-store, no-cache, must-revalidate"
    )

    return response
import re
import secrets

from django.conf import settings
from django.db import transaction

from apps.ghl.models import GHLInstallation

from .client import EvolutionAPIError, EvolutionClient
from .models import EvolutionInstance


def generate_instance_name(location_id: str) -> str:
    """
    Produit un nom Evolution stable à partir du Location ID GHL.
    """

    cleaned_location_id = re.sub(
        r"[^a-zA-Z0-9_-]",
        "-",
        location_id,
    )

    return f"ghl-{cleaned_location_id}"[:120]

def normalize_instance_status(status: str | None) -> str:
    normalized_status = (status or "").strip().lower()

    aliases = {
        "connected": EvolutionInstance.Status.OPEN,
        "disconnected": EvolutionInstance.Status.CLOSE,
        "closed": EvolutionInstance.Status.CLOSE,
        "qr": EvolutionInstance.Status.CONNECTING,
        "pairing": EvolutionInstance.Status.CONNECTING,
    }

    normalized_status = aliases.get(
        normalized_status,
        normalized_status,
    )

    allowed_statuses = {
        EvolutionInstance.Status.CREATED,
        EvolutionInstance.Status.CONNECTING,
        EvolutionInstance.Status.OPEN,
        EvolutionInstance.Status.CLOSE,
        EvolutionInstance.Status.ERROR,
    }

    if normalized_status in allowed_statuses:
        return normalized_status

    return EvolutionInstance.Status.CREATED


def provision_evolution_instance(
    installation: GHLInstallation | int,
) -> tuple[EvolutionInstance, bool]:
    """
    Retourne l'instance Evolution existante ou en crée une nouvelle.

    Important :
    une instance existante ne doit jamais être recréée simplement
    parce que son statut local est ERROR, CLOSE ou CONNECTING.
    """

    installation_id = (
        installation.pk
        if isinstance(installation, GHLInstallation)
        else installation
    )

    with transaction.atomic():
        locked_installation = (
            GHLInstallation.objects
            .select_for_update()
            .get(pk=installation_id)
        )

        existing_instance = (
            EvolutionInstance.objects
            .select_for_update()
            .filter(installation=locked_installation)
            .first()
        )

        # L'instance existe déjà dans PostgreSQL :
        # on la réutilise, quel que soit son statut actuel.
        if existing_instance:
            return existing_instance, False

        evolution_instance = EvolutionInstance.objects.create(
            installation=locked_installation,
            instance_name=generate_instance_name(
                locked_installation.location_id
            ),
            integration=settings.EVOLUTION_INTEGRATION,
            instance_api_key=secrets.token_hex(32),
            status=EvolutionInstance.Status.CREATED,
        )

    client = EvolutionClient()

    try:
        response_data = client.create_instance(
            instance_name=evolution_instance.instance_name,
            instance_token=evolution_instance.instance_api_key,
            integration=evolution_instance.integration,
            qrcode=True,
        )

    except EvolutionAPIError as exc:
        evolution_instance.status = EvolutionInstance.Status.ERROR
        evolution_instance.last_error = str(exc)

        if exc.details:
            evolution_instance.last_error += f" — {exc.details}"

        evolution_instance.save(
            update_fields=[
                "status",
                "last_error",
                "updated_at",
            ]
        )

        raise

    remote_instance = response_data.get("instance") or {}

    evolution_instance.remote_instance_id = (
        remote_instance.get("instanceId")
        or remote_instance.get("instance_id")
        or ""
    )

    evolution_instance.status = normalize_instance_status(
        remote_instance.get("status")
    )

    returned_instance_key = response_data.get("hash")

    if returned_instance_key:
        evolution_instance.instance_api_key = returned_instance_key

    evolution_instance.metadata = {
        "instance": {
            "instanceName": remote_instance.get("instanceName"),
            "integration": remote_instance.get("integration"),
            "status": remote_instance.get("status"),
        },
        "settings": response_data.get("settings") or {},
    }

    evolution_instance.last_error = ""

    evolution_instance.save(
        update_fields=[
            "remote_instance_id",
            "instance_api_key",
            "status",
            "metadata",
            "last_error",
            "updated_at",
        ]
    )

    return evolution_instance, True
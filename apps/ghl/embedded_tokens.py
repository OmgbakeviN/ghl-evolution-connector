from typing import Any

from django.conf import settings
from django.core import signing


EMBEDDED_TOKEN_SALT = "ghl-evolution.embedded-session.v1"


class GHLEmbeddedTokenError(Exception):
    """Erreur de validation d'un jeton de Custom Page."""


class GHLEmbeddedTokenExpired(GHLEmbeddedTokenError):
    """Le jeton de Custom Page a expiré."""


def create_embedded_token(
    *,
    location_id: str,
    user_id: str,
    role: str,
    company_id: str = "",
) -> str:
    """
    Crée un jeton signé temporaire pour la Custom Page.

    Aucun token OAuth ou secret ne doit être placé dans ce payload.
    """

    payload = {
        "purpose": "ghl_embedded_dashboard",
        "location_id": location_id,
        "user_id": user_id,
        "role": role,
        "company_id": company_id,
    }

    return signing.dumps(
        payload,
        salt=EMBEDDED_TOKEN_SALT,
        compress=True,
    )


def decode_embedded_token(
    token: str,
) -> dict[str, Any]:
    """
    Vérifie la signature et l'expiration du jeton.
    """

    if not token:
        raise GHLEmbeddedTokenError(
            "Le jeton de la Custom Page est absent."
        )

    try:
        payload = signing.loads(
            token,
            salt=EMBEDDED_TOKEN_SALT,
            max_age=settings.GHL_EMBEDDED_TOKEN_MAX_AGE,
        )

    except signing.SignatureExpired as exc:
        raise GHLEmbeddedTokenExpired(
            "La session de la Custom Page a expiré."
        ) from exc

    except signing.BadSignature as exc:
        raise GHLEmbeddedTokenError(
            "Le jeton de la Custom Page est invalide."
        ) from exc

    if not isinstance(payload, dict):
        raise GHLEmbeddedTokenError(
            "Le contenu du jeton est invalide."
        )

    if payload.get("purpose") != "ghl_embedded_dashboard":
        raise GHLEmbeddedTokenError(
            "Le jeton n'est pas destiné à cette fonctionnalité."
        )

    required_fields = (
        "location_id",
        "user_id",
        "role",
    )

    missing_fields = [
        field
        for field in required_fields
        if not payload.get(field)
    ]

    if missing_fields:
        raise GHLEmbeddedTokenError(
            "Le jeton est incomplet. Champs absents : "
            + ", ".join(missing_fields)
        )

    return payload
from datetime import timedelta
from typing import Any

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import GHLInstallation


TOKEN_REFRESH_MARGIN = timedelta(minutes=5)


class GHLOAuthError(Exception):
    """Erreur pendant une opération OAuth HighLevel."""


def _normalize_token_response(raw_data: dict[str, Any]) -> dict[str, Any]:
    """
    Accepte les réponses HighLevel en camelCase ou snake_case.
    """

    return {
        "access_token": (
            raw_data.get("accessToken")
            or raw_data.get("access_token")
        ),
        "refresh_token": (
            raw_data.get("refreshToken")
            or raw_data.get("refresh_token")
        ),
        "expires_in": (
            raw_data.get("expiresIn")
            if raw_data.get("expiresIn") is not None
            else raw_data.get("expires_in")
        ),
        "token_type": (
            raw_data.get("tokenType")
            or raw_data.get("token_type")
            or "Bearer"
        ),
        "scope": raw_data.get("scope") or "",
        "userType": raw_data.get("userType"),
        "locationId": raw_data.get("locationId"),
        "companyId": raw_data.get("companyId"),
        "userId": raw_data.get("userId"),
    }


def _request_oauth_token(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Envoie une demande de token à HighLevel.

    Le corps est envoyé en application/x-www-form-urlencoded.
    """

    if not settings.GHL_CLIENT_ID:
        raise GHLOAuthError("GHL_CLIENT_ID n'est pas configuré.")

    if not settings.GHL_CLIENT_SECRET:
        raise GHLOAuthError("GHL_CLIENT_SECRET n'est pas configuré.")

    headers = {
        "Accept": "application/json",
        "Version": getattr(settings, "GHL_API_VERSION", "v3"),
    }

    try:
        response = requests.post(
            settings.GHL_TOKEN_URL,
            data=payload,
            headers=headers,
            timeout=30,
        )
    except requests.RequestException as exc:
        raise GHLOAuthError(
            "Impossible de contacter le service OAuth HighLevel."
        ) from exc

    if not response.ok:
        try:
            error_details = response.json()
        except ValueError:
            error_details = response.text[:500]

        raise GHLOAuthError(
            "HighLevel a refusé la demande OAuth : "
            f"HTTP {response.status_code} - {error_details}"
        )

    try:
        raw_data = response.json()
    except ValueError as exc:
        raise GHLOAuthError(
            "HighLevel a retourné une réponse JSON invalide."
        ) from exc

    token_data = _normalize_token_response(raw_data)

    required_fields = (
        "access_token",
        "refresh_token",
        "expires_in",
    )

    missing_fields = [
        field
        for field in required_fields
        if token_data.get(field) in (None, "")
    ]

    if missing_fields:
        raise GHLOAuthError(
            "Réponse OAuth incomplète. Champs manquants : "
            + ", ".join(missing_fields)
        )

    try:
        token_data["expires_in"] = int(token_data["expires_in"])
    except (TypeError, ValueError) as exc:
        raise GHLOAuthError(
            "La durée de validité du token est invalide."
        ) from exc

    return token_data


def exchange_authorization_code(code: str) -> dict[str, Any]:
    """
    Échange le code reçu après l'installation contre les premiers tokens.
    """

    if not settings.GHL_REDIRECT_URI:
        raise GHLOAuthError("GHL_REDIRECT_URI n'est pas configuré.")

    payload = {
        "clientId": settings.GHL_CLIENT_ID,
        "clientSecret": settings.GHL_CLIENT_SECRET,
        "grantType": "authorization_code",
        "code": code,
        "userType": "Location",
        "redirectUri": settings.GHL_REDIRECT_URI,
    }

    token_data = _request_oauth_token(payload)

    if not token_data.get("userType"):
        raise GHLOAuthError(
            "La réponse OAuth ne contient pas le type d'utilisateur."
        )

    return token_data


def request_refreshed_token(
    refresh_token: str,
    user_type: str = "Location",
) -> dict[str, Any]:
    """
    Échange un refresh token contre une nouvelle paire de tokens.
    """

    if not refresh_token:
        raise GHLOAuthError(
            "Aucun refresh token n'est disponible."
        )

    payload = {
        "clientId": settings.GHL_CLIENT_ID,
        "clientSecret": settings.GHL_CLIENT_SECRET,
        "grantType": "refresh_token",
        "refreshToken": refresh_token,
        "userType": user_type or "Location",
        "redirectUri": settings.GHL_REDIRECT_URI,
    }

    return _request_oauth_token(payload)


def refresh_installation_tokens(
    installation_id: int,
    *,
    force: bool = False,
) -> GHLInstallation:
    """
    Rafraîchit les tokens d'une installation.

    select_for_update empêche deux requêtes simultanées
    d'utiliser le même refresh token.
    """

    with transaction.atomic():
        installation = (
            GHLInstallation.objects
            .select_for_update()
            .get(pk=installation_id)
        )

        if not installation.is_active:
            raise GHLOAuthError(
                "Cette installation HighLevel est inactive."
            )

        refresh_deadline = timezone.now() + TOKEN_REFRESH_MARGIN

        # Une autre requête a peut-être déjà rafraîchi le token
        # pendant que celle-ci attendait le verrou PostgreSQL.
        if (
            not force
            and installation.expires_at > refresh_deadline
        ):
            return installation

        token_data = request_refreshed_token(
            refresh_token=installation.refresh_token,
            user_type=installation.user_type,
        )

        returned_location_id = token_data.get("locationId")

        if (
            returned_location_id
            and returned_location_id != installation.location_id
        ):
            raise GHLOAuthError(
                "Le token rafraîchi appartient à un autre sous-compte."
            )

        installation.access_token = token_data["access_token"]
        installation.refresh_token = token_data["refresh_token"]
        installation.token_type = token_data["token_type"]
        installation.expires_at = (
            timezone.now()
            + timedelta(seconds=token_data["expires_in"])
        )

        if token_data.get("scope"):
            installation.scopes = token_data["scope"]

        if token_data.get("companyId"):
            installation.company_id = token_data["companyId"]

        if token_data.get("userId"):
            installation.user_id = token_data["userId"]

        if token_data.get("userType"):
            installation.user_type = token_data["userType"]

        installation.save(
            update_fields=[
                "access_token",
                "refresh_token",
                "token_type",
                "expires_at",
                "scopes",
                "company_id",
                "user_id",
                "user_type",
                "updated_at",
            ]
        )

        return installation


def get_valid_access_token(
    installation: GHLInstallation | int,
) -> str:
    """
    Retourne un access token utilisable.

    Le token est automatiquement rafraîchi lorsqu'il expire
    dans moins de cinq minutes.
    """

    installation_id = (
        installation.pk
        if isinstance(installation, GHLInstallation)
        else installation
    )

    current = GHLInstallation.objects.get(pk=installation_id)

    if not current.is_active:
        raise GHLOAuthError(
            "Cette installation HighLevel est inactive."
        )

    refresh_deadline = timezone.now() + TOKEN_REFRESH_MARGIN

    if current.expires_at > refresh_deadline:
        return current.access_token

    refreshed = refresh_installation_tokens(installation_id)

    return refreshed.access_token
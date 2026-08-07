from datetime import timedelta

from django.utils import timezone
from django.conf import settings
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import GHLInstallation
from .services import GHLOAuthError, exchange_authorization_code
from .sso import (
    GHLUserContextError,
    decrypt_user_context
)
from .embedded_tokens import create_embedded_token

import logging

logger = logging.getLogger(__name__)


@api_view(["GET"])
def health_check(request):
    return Response(
        {
            "status": "ok",
            "service": "ghl-evolution-connector",
        }
    )

@api_view(["GET"])
@permission_classes([AllowAny])
def oauth_callback(request):
    """
    Callback appelé par HighLevel après l'installation de l'application.
    Exemple :
    /api/ghl/oauth/callback/?code=abc123
    """

    authorization_error = request.query_params.get("error")

    if authorization_error:
        return Response(
            {
                "status": "error",
                "message": "L'autorisation HighLevel a été refusée.",
                "error": authorization_error,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    code = request.query_params.get("code")

    if not code:
        return Response(
            {
                "status": "error",
                "message": "Le paramètre OAuth 'code' est absent.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        token_data = exchange_authorization_code(code)
    except GHLOAuthError as exc:
        return Response(
            {
                "status": "error",
                "message": str(exc),
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    user_type = token_data.get("userType", "")
    location_id = token_data.get("locationId")

    if user_type != "Location":
        return Response(
            {
                "status": "error",
                "message": (
                    "HighLevel a retourné un token Agency/Company au lieu "
                    "d'un token Location. Installe l'application depuis "
                    "un utilisateur du sous-compte pour ce premier test."
                ),
                "user_type": user_type,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not location_id:
        return Response(
            {
                "status": "error",
                "message": "La réponse HighLevel ne contient pas de locationId.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    expires_in = int(token_data.get("expires_in", 86400))
    expires_at = timezone.now() + timedelta(seconds=expires_in)

    installation, created = GHLInstallation.objects.update_or_create(
        location_id=location_id,
        defaults={
            "company_id": token_data.get("companyId") or "",
            "user_id": token_data.get("userId") or "",
            "user_type": user_type,
            "access_token": token_data["access_token"],
            "refresh_token": token_data["refresh_token"],
            "token_type": token_data.get("token_type", "Bearer"),
            "scopes": token_data.get("scope") or "",
            "expires_at": expires_at,
            "is_active": True,
        },
    )

    try:
        from apps.evolution.services import (
            provision_evolution_instance,
        )

        provision_evolution_instance(installation)

    except Exception:
        # L'OAuth reste valide même si Evolution API est
        # momentanément indisponible. La Custom Page réessaiera.
        logger.exception(
            "Échec du provisionnement Evolution pour la Location %s",
            installation.location_id,
        )

    return redirect("ghl:oauth-success")

@require_GET
def oauth_success(request):
    return render(
        request,
        "ghl/oauth_success.html",
    )

@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def user_context(request):
    """
    Valide le contexte chiffré provenant d'une Custom Page HighLevel.
    """

    encrypted_data = request.data.get("encryptedData")

    if not encrypted_data:
        return Response(
            {
                "success": False,
                "message": "Le champ encryptedData est obligatoire.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        context = decrypt_user_context(
            encrypted_data=encrypted_data,
            shared_secret=settings.GHL_SHARED_SECRET,
        )
    except GHLUserContextError as exc:
        return Response(
            {
                "success": False,
                "message": str(exc),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    location_id = context.get("activeLocation")

    if not location_id:
        return Response(
            {
                "success": False,
                "message": (
                    "Aucun sous-compte actif n'a été trouvé "
                    "dans le contexte HighLevel."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    installation = GHLInstallation.objects.filter(
        location_id=location_id,
        is_active=True,
    ).first()

    role = str(
        context.get("role") or ""
    ).strip().lower()

    user_id = str(
        context.get("userId") or ""
    ).strip()

    if not user_id:
        return Response(
            {
                "success": False,
                "message": (
                    "Le contexte HighLevel ne contient "
                    "aucun identifiant utilisateur."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Pour le moment, seuls les administrateurs peuvent
    # connecter ou consulter le compte WhatsApp.
    if role != "admin":
        return Response(
            {
                "success": False,
                "message": (
                    "Seuls les administrateurs du sous-compte "
                    "peuvent configurer la connexion WhatsApp."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    embedded_token = create_embedded_token(
        location_id=location_id,
        user_id=user_id,
        role=role,
        company_id=str(
            context.get("companyId") or ""
        ),
    )

    if installation is None:
        return Response(
            {
                "success": False,
                "message": (
                    "L'application n'est pas installée ou active "
                    "pour ce sous-compte."
                ),
                "location_id": location_id,
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(
        {
            "success": True,
            "message": "Contexte HighLevel validé.",
            "location_id": location_id,
            "company_id": context.get("companyId"),
            "user": {
                "id": context.get("userId"),
                "name": context.get("userName"),
                "email": context.get("email"),
                "role": context.get("role"),
                "is_agency_owner": context.get(
                    "isAgencyOwner",
                    False,
                ),
            },
            "installation": {
                "id": installation.pk,
                "active": installation.is_active,
            },
            "embedded_token": embedded_token,
            "embedded_token_expires_in": (settings.GHL_EMBEDDED_TOKEN_MAX_AGE, ),
        },
        status=status.HTTP_200_OK,
    )
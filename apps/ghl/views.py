from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import GHLInstallation
from .services import GHLOAuthError, exchange_authorization_code


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

    return Response(
        {
            "status": "connected",
            "message": "L'application HighLevel est correctement installée.",
            "location_id": installation.location_id,
            "created": created,
            "expires_at": installation.expires_at,
        },
        status=status.HTTP_200_OK,
    )
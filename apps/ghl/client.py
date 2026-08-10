from typing import Any

import requests
from django.conf import settings

from .models import GHLInstallation
from .services import get_valid_access_token


class GHLAPIError(Exception):
    """Erreur lors d'un appel à l'API HighLevel."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)

        self.status_code = status_code
        self.details = details


class GHLClient:
    BASE_URL = "https://services.leadconnectorhq.com"

    def __init__(
        self,
        installation: GHLInstallation,
        timeout: int = 30,
    ) -> None:
        self.installation = installation
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:

        access_token = get_valid_access_token(
            self.installation.pk
        )

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Version": getattr(
                settings,
                "GHL_API_VERSION",
                "v3",
            ),
        }

        if json is not None:
            headers["Content-Type"] = "application/json"

        url = (
            f"{self.BASE_URL}/"
            f"{path.lstrip('/')}"
        )

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=json,
                params=params,
                timeout=self.timeout,
            )

        except requests.RequestException as exc:
            raise GHLAPIError(
                "Impossible de contacter l'API HighLevel."
            ) from exc

        try:
            response_data = response.json()
        except ValueError:
            response_data = {
                "raw_response": response.text[:1000]
            }

        if not response.ok:
            raise GHLAPIError(
                (
                    "HighLevel a refusé la requête : "
                    f"HTTP {response.status_code}"
                ),
                status_code=response.status_code,
                details=response_data,
            )

        if not isinstance(response_data, dict):
            raise GHLAPIError(
                "HighLevel a retourné une réponse inattendue."
            )

        return response_data

    def search_contacts(
        self,
        *,
        query: str = "",
        page: int = 1,
        page_limit: int = 50,
    ) -> dict[str, Any]:
        """
        Recherche les contacts appartenant à la Location
        de cette installation.
        """

        page = max(page, 1)

        page_limit = max(
            1,
            min(page_limit, 500),
        )

        payload = {
            "locationId": self.installation.location_id,
            "page": page,
            "pageLimit": page_limit,
        }

        if query.strip():
            payload["query"] = query.strip()[:75]

        return self._request(
            "POST",
            "/contacts/search",
            json=payload,
        )
    
    def get_contact(
        self,
        contact_id: str,
    ) -> dict[str, Any]:

        contact_id = str(contact_id).strip()

        if not contact_id:
            raise GHLAPIError(
                "L'identifiant du contact est obligatoire."
            )

        result = self._request(
            "GET",
            f"/contacts/{contact_id}",
        )

        contact = result.get("contact")

        if isinstance(contact, dict):
            return contact

        # Compatibilité si GHL retourne directement
        # l'objet contact.
        return result

    def get_contact(
        self,
        contact_id: str,
    ) -> dict[str, Any]:

        contact_id = str(contact_id).strip()

        if not contact_id:
            raise GHLAPIError(
                "L'identifiant du contact est obligatoire."
            )

        result = self._request(
            "GET",
            f"/contacts/{contact_id}",
        )

        contact = result.get("contact")

        if isinstance(contact, dict):
            return contact

        # Compatibilité si GHL retourne directement
        # l'objet contact.
        return result



from typing import Any
from urllib.parse import quote

import requests
from django.conf import settings


class EvolutionAPIError(Exception):
    """Erreur lors d'un appel à Evolution API."""

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


class EvolutionClient:
    """
    Client HTTP centralisé pour Evolution API.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int = 30,
    ) -> None:
        self.base_url = (
            base_url or settings.EVOLUTION_API_URL
        ).rstrip("/")

        self.api_key = api_key or settings.EVOLUTION_API_KEY
        self.timeout = timeout

        if not self.base_url:
            raise EvolutionAPIError(
                "EVOLUTION_API_URL n'est pas configuré."
            )

        if not self.api_key:
            raise EvolutionAPIError(
                "EVOLUTION_API_KEY n'est pas configuré."
            )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        api_key: str | None = None,
        expected_statuses: tuple[int, ...] = (200,),
    ) -> dict[str, Any] | list[Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"

        headers = {
            "apikey": api_key or self.api_key,
            "Accept": "application/json",
        }

        if json is not None:
            headers["Content-Type"] = "application/json"

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=json,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise EvolutionAPIError(
                "Impossible de contacter Evolution API."
            ) from exc

        try:
            response_data = response.json()
        except ValueError:
            response_data = {
                "raw_response": response.text[:1000],
            }

        if response.status_code not in expected_statuses:
            raise EvolutionAPIError(
                (
                    "Evolution API a refusé la requête : "
                    f"HTTP {response.status_code}"
                ),
                status_code=response.status_code,
                details=response_data,
            )

        return response_data

    def create_instance(
        self,
        *,
        instance_name: str,
        instance_token: str,
        integration: str = "WHATSAPP-BAILEYS",
        qrcode: bool = True,
    ) -> dict[str, Any]:
        payload = {
            "instanceName": instance_name,
            "integration": integration,
            "qrcode": qrcode,
            "token": instance_token,
        }

        result = self._request(
            "POST",
            "/instance/create",
            json=payload,
            expected_statuses=(200, 201),
        )

        if not isinstance(result, dict):
            raise EvolutionAPIError(
                "Evolution API a retourné une réponse inattendue."
            )

        return result

    def connect_instance(
        self,
        instance_name: str,
    ) -> dict[str, Any]:
        safe_name = quote(instance_name, safe="")

        result = self._request(
            "GET",
            f"/instance/connect/{safe_name}",
            expected_statuses=(200,),
        )

        if not isinstance(result, dict):
            raise EvolutionAPIError(
                "La réponse du QR Code est invalide."
            )

        return result

    def get_connection_state(
        self,
        instance_name: str,
    ) -> dict[str, Any]:
        safe_name = quote(instance_name, safe="")

        result = self._request(
            "GET",
            f"/instance/connectionState/{safe_name}",
            expected_statuses=(200,),
        )

        if not isinstance(result, dict):
            raise EvolutionAPIError(
                "La réponse de l'état de connexion est invalide."
            )

        return result
    

    def set_webhook(
        self,
        *,
        instance_name: str,
        url: str,
        events: list[str],
    ) -> dict[str, Any]:
        """
        Configure le webhook d'une instance Evolution API 2.3.7.
        """

        safe_name = quote(
            instance_name,
            safe="",
        )

        payload = {
            "webhook": {
                "enabled": True,
                "url": url,
                "headers": {},
                "byEvents": False,
                "base64": False,
                "events": events,
            }
        }

        result = self._request(
            "POST",
            f"/webhook/set/{safe_name}",
            json=payload,
            expected_statuses=(200, 201),
        )

        if not isinstance(result, dict):
            raise EvolutionAPIError(
                "La réponse de configuration webhook est invalide."
            )

        return result


    def find_webhook(
        self,
        instance_name: str,
    ) -> dict[str, Any]:
        """
        Retourne la configuration webhook actuelle.
        """

        safe_name = quote(
            instance_name,
            safe="",
        )

        result = self._request(
            "GET",
            f"/webhook/find/{safe_name}",
            expected_statuses=(200,),
        )

        if not isinstance(result, dict):
            raise EvolutionAPIError(
                "La configuration webhook retournée est invalide."
            )

        return result
    
    def check_whatsapp_numbers(
        self,
        *,
        instance_name: str,
        numbers: list[str],
    ) -> list[dict[str, Any]]:
        """
        Vérifie quels numéros possèdent un compte WhatsApp.
        """

        safe_name = quote(
            instance_name,
            safe="",
        )

        clean_numbers = [
            str(number).strip()
            for number in numbers
            if str(number).strip()
        ]

        if not clean_numbers:
            return []

        payload = {
            "numbers": clean_numbers,
        }

        result = self._request(
            "POST",
            f"/chat/whatsappNumbers/{safe_name}",
            json=payload,
            expected_statuses=(200, 201),
        )

        # Evolution retourne généralement une liste.
        if isinstance(result, list):
            return result

        # Compatibilité avec certaines variantes de réponse.
        if isinstance(result, dict):

            for key in (
                "data",
                "numbers",
                "result",
                "response",
            ):
                value = result.get(key)

                if isinstance(value, list):
                    return value

        raise EvolutionAPIError(
            "Evolution API a retourné un format "
            "inattendu pour whatsappNumbers."
        )

    def send_text(
        self,
        *,
        instance_name: str,
        number: str,
        text: str,
        delay_ms: int = 1000,
    ):
        safe_name = quote(
            instance_name,
            safe="",
        )

        number = str(
            number or ""
        ).strip()

        text = str(
            text or ""
        ).strip()

        if not number:
            raise EvolutionAPIError(
                "Le numéro WhatsApp est obligatoire."
            )

        if not text:
            raise EvolutionAPIError(
                "Le message WhatsApp est vide."
            )

        payload = {
            "number": number,
            "text": text,
            "delay": max(
                0,
                int(delay_ms),
            ),
        }

        return self._request(
            "POST",
            f"/message/sendText/{safe_name}",
            json=payload,
            expected_statuses=(
                200,
                201,
            ),
        )
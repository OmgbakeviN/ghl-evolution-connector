import base64
import hashlib
import json
from typing import Any

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


class GHLUserContextError(Exception):
    """Erreur de déchiffrement du contexte utilisateur HighLevel."""


def _derive_key_and_iv(
    password: bytes,
    salt: bytes,
    *,
    key_size: int = 32,
    iv_size: int = 16,
) -> tuple[bytes, bytes]:
    """
    Reproduit la dérivation de clé OpenSSL/CryptoJS utilisée
    par le contexte chiffré HighLevel.
    """

    generated = b""
    previous_block = b""

    while len(generated) < key_size + iv_size:
        previous_block = hashlib.md5(
            previous_block + password + salt
        ).digest()

        generated += previous_block

    key = generated[:key_size]
    iv = generated[key_size:key_size + iv_size]

    return key, iv


def decrypt_user_context(
    encrypted_data: str,
    shared_secret: str,
) -> dict[str, Any]:
    """
    Déchiffre le contexte envoyé par HighLevel.

    Format attendu :
        Salted__ + salt + ciphertext
    encodé en Base64.
    """

    if not encrypted_data:
        raise GHLUserContextError(
            "Le contexte HighLevel est absent."
        )

    if not shared_secret:
        raise GHLUserContextError(
            "GHL_SHARED_SECRET n'est pas configuré."
        )

    try:
        raw_data = base64.b64decode(
            encrypted_data,
            validate=True,
        )
    except (ValueError, TypeError) as exc:
        raise GHLUserContextError(
            "Le contexte HighLevel n'est pas un Base64 valide."
        ) from exc

    if len(raw_data) < 32:
        raise GHLUserContextError(
            "Le contexte HighLevel est trop court."
        )

    if raw_data[:8] != b"Salted__":
        raise GHLUserContextError(
            "Le format du contexte HighLevel est invalide."
        )

    salt = raw_data[8:16]
    ciphertext = raw_data[16:]

    if len(ciphertext) % AES.block_size != 0:
        raise GHLUserContextError(
            "La taille du contexte chiffré est invalide."
        )

    key, iv = _derive_key_and_iv(
        shared_secret.encode("utf-8"),
        salt,
    )

    try:
        cipher = AES.new(
            key,
            AES.MODE_CBC,
            iv,
        )

        decrypted_bytes = cipher.decrypt(ciphertext)

        plaintext = unpad(
            decrypted_bytes,
            AES.block_size,
        ).decode("utf-8")

        context = json.loads(plaintext)

    except (
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise GHLUserContextError(
            "Impossible de déchiffrer le contexte HighLevel."
        ) from exc

    if not isinstance(context, dict):
        raise GHLUserContextError(
            "Le contexte HighLevel doit être un objet JSON."
        )

    return context
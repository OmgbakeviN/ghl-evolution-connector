import base64
import binascii

from Crypto.PublicKey import ECC
from Crypto.Signature import eddsa


GHL_PROVIDER_PUBLIC_KEY = """
-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAi2HR1srL4o18O8BRa7gVJY7G7bupbN3H9AwJrHCDiOg=
-----END PUBLIC KEY-----
""".strip()


def verify_ghl_provider_signature(
    raw_body: bytes,
    signature: str,
) -> bool:

    if not raw_body:
        return False

    signature = str(
        signature or ""
    ).strip()

    if not signature:
        return False

    try:

        signature_bytes = (
            base64.b64decode(
                signature,
                validate=True,
            )
        )

        public_key = ECC.import_key(
            GHL_PROVIDER_PUBLIC_KEY
        )

        verifier = eddsa.new(
            public_key,
            mode="rfc8032",
        )

        verifier.verify(
            raw_body,
            signature_bytes,
        )

        return True

    except (
        ValueError,
        TypeError,
        binascii.Error,
    ):
        return False
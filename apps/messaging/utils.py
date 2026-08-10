import re


def normalize_phone(phone: str) -> str:
    """
    +237 620-464-907
        ->
    237620464907
    """

    return re.sub(
        r"\D",
        "",
        str(phone or ""),
    )


from pathlib import Path


MAX_CAMPAIGN_ATTACHMENTS = 5

MAX_ATTACHMENT_SIZE = (
    5 * 1024 * 1024
)


IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
}


DOCUMENT_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/csv",

    "application/msword",

    (
        "application/vnd.openxmlformats-"
        "officedocument.wordprocessingml.document"
    ),

    "application/vnd.ms-excel",

    (
        "application/vnd.openxmlformats-"
        "officedocument.spreadsheetml.sheet"
    ),

    "application/vnd.ms-powerpoint",

    (
        "application/vnd.openxmlformats-"
        "officedocument.presentationml.presentation"
    ),

    "application/zip",
}


def validate_campaign_file(
    uploaded_file,
):

    if (
        uploaded_file.size
        > MAX_ATTACHMENT_SIZE
    ):
        raise ValueError(
            (
                f"{uploaded_file.name} dépasse "
                "la limite de 5 Mo."
            )
        )

    mime_type = str(
        uploaded_file.content_type
        or ""
    ).lower()

    if mime_type in IMAGE_MIME_TYPES:
        return "image"

    if mime_type in DOCUMENT_MIME_TYPES:
        return "document"

    raise ValueError(
        (
            f"Type de fichier non supporté : "
            f"{mime_type or Path(uploaded_file.name).suffix}"
        )
    )
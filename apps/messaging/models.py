from django.db import models


class BulkCampaign(models.Model):

    class Status(models.TextChoices):
        DRAFT = "draft", "Brouillon"
        QUEUED = "queued", "En attente"
        RUNNING = "running", "En cours"
        COMPLETED = "completed", "Terminée"
        PARTIAL = "partial", "Partiellement terminée"
        FAILED = "failed", "Échec"
        CANCELLED = "cancelled", "Annulée"

    installation = models.ForeignKey(
        "ghl.GHLInstallation",
        on_delete=models.CASCADE,
        related_name="bulk_campaigns",
    )

    name = models.CharField(
        max_length=255,
    )

    message_template = models.TextField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )

    created_by_highlevel_user_id = models.CharField(
        max_length=120,
    )

    total_contacts = models.PositiveIntegerField(
        default=0,
    )

    validated_count = models.PositiveIntegerField(
        default=0,
    )

    not_on_whatsapp_count = models.PositiveIntegerField(
        default=0,
    )

    validation_error_count = models.PositiveIntegerField(
        default=0,
    )

    sent_count = models.PositiveIntegerField(
        default=0,
    )

    failed_count = models.PositiveIntegerField(
        default=0,
    )

    skipped_count = models.PositiveIntegerField(
        default=0,
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return f"{self.name} - {self.status}"


class BulkCampaignRecipient(models.Model):

    class ProviderDeliveryStatus(models.TextChoices):
        PENDING = "pending", "En attente GHL"
        SUBMITTED = "submitted", "Transmis à GHL"
        SENT = "sent", "Envoyé par le provider"
        FAILED = "failed", "Échec du provider"

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"

        VALIDATING = (
            "validating",
            "Vérification WhatsApp",
        )

        READY = (
            "ready",
            "Prêt à envoyer",
        )

        PROCESSING = (
            "processing",
            "En cours",
        )

        SENT = ("sent", "Envoyé",)

        FAILED = ("failed", "Échec",)   

        SKIPPED = (
            "skipped",
            "Ignoré",
        )

        NOT_ON_WHATSAPP = (
            "not_on_whatsapp",
            "Pas sur WhatsApp",
        )

    campaign = models.ForeignKey(
        BulkCampaign,
        on_delete=models.CASCADE,
        related_name="recipients",
    )

    ghl_contact_id = models.CharField(
        max_length=120,
    )

    first_name = models.CharField(
        max_length=255,
        blank=True,
    )

    last_name = models.CharField(
        max_length=255,
        blank=True,
    )

    email = models.EmailField(
        blank=True,
    )

    phone = models.CharField(
        max_length=50,
    )

    normalized_phone = models.CharField(
        max_length=30,
    )

    # Vérification WhatsApp
    is_on_whatsapp = models.BooleanField(
        null=True,
        blank=True,
    )

    whatsapp_jid = models.CharField(
        max_length=150,
        blank=True,
    )

    whatsapp_checked_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    whatsapp_check_error = models.TextField(
        blank=True,
    )

    # Message final personnalisé
    rendered_message = models.TextField(
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    evolution_message_id = models.CharField(
        max_length=255,
        blank=True,
    )

    attempts = models.PositiveIntegerField(
        default=0,
    )

    last_error = models.TextField(
        blank=True,
    )

    sent_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    ghl_message_id = models.CharField(
        max_length=150,
        null=True,
        blank=True,
        unique=True,
    )

    ghl_conversation_id = models.CharField(
        max_length=150,
        null=True,
        blank=True,
    )

    ghl_history_synced_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    provider_delivery_status = models.CharField(
        max_length=20,
        choices=ProviderDeliveryStatus.choices,
        default=ProviderDeliveryStatus.PENDING,
        db_index=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "campaign",
                    "ghl_contact_id",
                ],
                name="unique_contact_per_bulk_campaign",
            ),
        ]

    def __str__(self):
        return (
            f"{self.ghl_contact_id} - "
            f"{self.campaign.name}"
        )
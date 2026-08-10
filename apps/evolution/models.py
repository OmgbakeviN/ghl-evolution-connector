from django.db import models


class EvolutionInstance(models.Model):
    """
    Instance WhatsApp Evolution API associée à une installation HighLevel.
    """

    class Status(models.TextChoices):
        CREATED = "created", "Créée"
        CONNECTING = "connecting", "Connexion en cours"
        OPEN = "open", "Connectée"
        CLOSE = "close", "Déconnectée"
        ERROR = "error", "Erreur"

    installation = models.OneToOneField(
        "ghl.GHLInstallation",
        on_delete=models.CASCADE,
        related_name="evolution_instance",
    )

    instance_name = models.CharField(
        max_length=120,
        unique=True,
    )

    remote_instance_id = models.CharField(
        max_length=150,
        blank=True,
    )

    integration = models.CharField(
        max_length=50,
        default="WHATSAPP-BAILEYS",
    )

    # Clé propre à cette instance, retournée ou utilisée
    # pendant sa création dans Evolution API.
    instance_api_key = models.TextField(
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CREATED,
    )

    phone_number = models.CharField(
        max_length=30,
        blank=True,
    )

    profile_name = models.CharField(
        max_length=255,
        blank=True,
    )

    webhook_url = models.URLField(
        blank=True,
    )

    webhook_secret = models.CharField(
    max_length=128,
    unique=True,
    null=True,
    blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    last_error = models.TextField(
        blank=True,
    )

    # Conserve certaines données retournées par Evolution API
    # pour le débogage, sans créer un champ pour chaque propriété.
    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    connected_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self) -> str:
        return f"{self.instance_name} — {self.status}"
    
class WebhookEvent(models.Model):

    class Status(models.TextChoices):
        RECEIVED = "received", "Reçu"
        PROCESSING = "processing", "En traitement"
        PROCESSED = "processed", "Traité"
        FAILED = "failed", "Échec"
        IGNORED = "ignored", "Ignoré"

    instance = models.ForeignKey(
        EvolutionInstance,
        on_delete=models.CASCADE,
        related_name="webhook_events",
    )

    event_type = models.CharField(
        max_length=100,
        db_index=True,
    )

    event_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
    )

    deduplication_key = models.CharField(
        max_length=64,
        unique=True,
    )

    payload = models.JSONField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RECEIVED,
        db_index=True,
    )

    attempts = models.PositiveIntegerField(
        default=0,
    )

    last_error = models.TextField(
        blank=True,
    )

    received_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    processed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    def __str__(self):
        return (
            f"{self.event_type} - "
            f"{self.instance.instance_name}"
        )
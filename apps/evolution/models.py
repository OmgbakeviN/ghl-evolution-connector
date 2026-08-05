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
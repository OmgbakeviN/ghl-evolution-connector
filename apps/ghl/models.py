from django.db import models


class GHLInstallation(models.Model):
    """
    Représente l'installation de l'application dans un sous-compte HighLevel.
    """

    location_id = models.CharField(
        max_length=100,
        unique=True,
    )

    company_id = models.CharField(
        max_length=100,
        blank=True,
    )

    user_id = models.CharField(
        max_length=100,
        blank=True,
    )

    user_type = models.CharField(
        max_length=30,
        default="Location",
    )

    access_token = models.TextField()

    refresh_token = models.TextField()

    token_type = models.CharField(
        max_length=30,
        default="Bearer",
    )

    scopes = models.TextField(blank=True)

    expires_at = models.DateTimeField()

    is_active = models.BooleanField(default=True)

    installed_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"HighLevel installation - {self.location_id}"
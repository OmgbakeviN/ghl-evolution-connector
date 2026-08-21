import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.messaging.services import (
    claim_next_bulk_recipient,
    process_bulk_recipient,
    claim_next_provider_outbound_job,
    process_provider_outbound_job,
)


class Command(BaseCommand):

    help = (
        "Worker d'envoi des campagnes WhatsApp bulk "
        "et des Delivery Jobs HighLevel."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help=(
                "Traite au maximum un envoi WhatsApp réel "
                "puis s'arrête."
            ),
        )

    def handle(self, *args, **options):

        once = options["once"]

        message_interval = max(
            1,
            int(
                getattr(
                    settings,
                    "BULK_MESSAGE_INTERVAL_SECONDS",
                    5,
                )
            ),
        )

        idle_seconds = max(
            1,
            int(
                getattr(
                    settings,
                    "BULK_WORKER_IDLE_SECONDS",
                    2,
                )
            ),
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Bulk WhatsApp worker démarré."
            )
        )

        self.stdout.write(
            (
                "Intervalle entre messages : "
                f"{message_interval}s"
            )
        )

        try:
            while True:

                close_old_connections()

                # -------------------------------------------------
                # PRIORITE 1 :
                # envoyer les Delivery Jobs déjà acceptés par GHL.
                # -------------------------------------------------
                provider_job_id = (
                    claim_next_provider_outbound_job()
                )

                if provider_job_id is not None:

                    self.stdout.write(
                        (
                            "Traitement provider job "
                            f"#{provider_job_id}"
                        )
                    )

                    try:
                        result = (
                            process_provider_outbound_job(
                                provider_job_id
                            )
                        )
                    except Exception as exc:
                        self.stderr.write(
                            self.style.ERROR(
                                (
                                    "Erreur provider job "
                                    f"#{provider_job_id}: "
                                    f"{exc}"
                                )
                            )
                        )

                        if once:
                            raise

                        time.sleep(message_interval)
                        continue

                    result_status = result.get(
                        "status"
                    )

                    if result_status in {
                        "sent",
                        "duplicate",
                    }:
                        self.stdout.write(
                            self.style.SUCCESS(
                                (
                                    "Provider job "
                                    f"#{provider_job_id}: "
                                    f"{result_status}"
                                )
                            )
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                (
                                    "Provider job "
                                    f"#{provider_job_id}: "
                                    f"{result_status} "
                                    f"{result.get('error', '')}"
                                )
                            )
                        )

                    # Le délai est placé après le vrai transport
                    # WhatsApp, pas après la simple soumission GHL.
                    if once:
                        return

                    time.sleep(message_interval)
                    continue

                # -------------------------------------------------
                # PRIORITE 2 :
                # soumettre le prochain recipient READY à GHL.
                # -------------------------------------------------
                recipient_id = (
                    claim_next_bulk_recipient()
                )

                if recipient_id is None:

                    if once:
                        self.stdout.write(
                            "Aucun message à envoyer."
                        )
                        return

                    time.sleep(idle_seconds)
                    continue

                self.stdout.write(
                    (
                        "Soumission recipient "
                        f"#{recipient_id} à HighLevel"
                    )
                )

                try:
                    result = (
                        process_bulk_recipient(
                            recipient_id
                        )
                    )

                except Exception as exc:
                    self.stderr.write(
                        self.style.ERROR(
                            (
                                "Erreur recipient "
                                f"#{recipient_id}: "
                                f"{exc}"
                            )
                        )
                    )

                    if once:
                        raise

                    time.sleep(idle_seconds)
                    continue

                result_status = result.get(
                    "status"
                )

                if result_status == "submitted_to_ghl":
                    self.stdout.write(
                        self.style.SUCCESS(
                            (
                                f"Recipient #{recipient_id} "
                                "accepté par HighLevel; "
                                "en attente du provider job."
                            )
                        )
                    )

                    # Pas de sleep ici : la prochaine boucle prend
                    # immédiatement le ProviderOutboundJob créé par
                    # la Delivery URL.
                    continue

                if result_status == "waiting_connection":
                    self.stdout.write(
                        self.style.WARNING(
                            "WhatsApp déconnecté. "
                            "Le recipient reste READY."
                        )
                    )

                    if once:
                        return

                    time.sleep(10)
                    continue

                self.stdout.write(
                    self.style.WARNING(
                        (
                            f"Recipient #{recipient_id}: "
                            f"{result_status} "
                            f"{result.get('error', '')}"
                        )
                    )
                )

                if once:
                    return

                time.sleep(idle_seconds)

        except KeyboardInterrupt:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "Bulk worker arrêté."
                )
            )

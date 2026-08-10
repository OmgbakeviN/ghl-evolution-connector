import time

from django.conf import settings
from django.core.management.base import (
    BaseCommand,
)
from django.db import close_old_connections

from apps.messaging.services import (
    claim_next_bulk_recipient,
    process_bulk_recipient,
)


class Command(BaseCommand):

    help = (
        "Worker d'envoi des campagnes "
        "WhatsApp bulk."
    )

    def add_arguments(
        self,
        parser,
    ):

        parser.add_argument(
            "--once",
            action="store_true",
            help=(
                "Traite au maximum un "
                "destinataire puis s'arrête."
            ),
        )

    def handle(
        self,
        *args,
        **options,
    ):

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
                f"Intervalle entre messages : "
                f"{message_interval}s"
            )
        )

        try:

            while True:

                close_old_connections()

                recipient_id = (
                    claim_next_bulk_recipient()
                )

                if recipient_id is None:

                    if once:
                        self.stdout.write(
                            "Aucun message à envoyer."
                        )
                        return

                    time.sleep(
                        idle_seconds
                    )

                    continue

                self.stdout.write(
                    (
                        "Traitement recipient "
                        f"#{recipient_id}"
                    )
                )

                try:

                    result = (
                        process_bulk_recipient(
                            recipient_id
                        )
                    )

                except Exception as exc:

                    #
                    # On ne tue pas le worker entier
                    # pour un seul contact.
                    #

                    self.stderr.write(
                        self.style.ERROR(
                            (
                                f"Erreur recipient "
                                f"#{recipient_id}: "
                                f"{exc}"
                            )
                        )
                    )

                    if once:
                        raise

                    time.sleep(
                        message_interval
                    )

                    continue

                status = result.get(
                    "status"
                )

                if status == "sent":

                    self.stdout.write(
                        self.style.SUCCESS(
                            (
                                f"Recipient "
                                f"#{recipient_id} envoyé."
                            )
                        )
                    )

                elif status == (
                    "waiting_connection"
                ):

                    self.stdout.write(
                        self.style.WARNING(
                            (
                                "WhatsApp déconnecté. "
                                "Le recipient reste READY."
                            )
                        )
                    )

                    if once:
                        return

                    time.sleep(10)

                    continue

                else:

                    self.stdout.write(
                        self.style.WARNING(
                            (
                                f"Recipient "
                                f"#{recipient_id}: "
                                f"{status}"
                            )
                        )
                    )

                if once:
                    return

                #
                # Délai entre deux messages.
                #
                time.sleep(
                    message_interval
                )

        except KeyboardInterrupt:

            self.stdout.write("")

            self.stdout.write(
                self.style.WARNING(
                    "Bulk worker arrêté."
                )
            )
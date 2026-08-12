# GHL Evolution WhatsApp Connector

Connecteur **GoHighLevel (HighLevel) + Evolution API + WhatsApp** construit avec **Django / Django REST Framework**.

L'application permet à un sous-compte HighLevel de connecter un numéro WhatsApp via Evolution API, sélectionner ses contacts GHL, créer et exécuter des campagnes WhatsApp bulk, vérifier les numéros avant envoi, suivre la progression des campagnes et enregistrer les messages envoyés dans l'historique des Conversations HighLevel via un **Custom Conversation Provider**.

---

## 1. Objectif du projet

Le projet fournit une application Marketplace HighLevel embarquée dans un sous-compte GHL.

Fonctionnalités principales actuellement disponibles :

- installation via OAuth 2.0 HighLevel ;
- association d'une installation GHL à une instance Evolution API ;
- connexion WhatsApp par QR Code ;
- affichage de l'état de connexion WhatsApp ;
- récupération des contacts HighLevel ;
- recherche et sélection multiple de contacts ;
- création de campagnes WhatsApp ;
- personnalisation du message avec des variables ;
- vérification des numéros WhatsApp avant envoi ;
- exclusion automatique des numéros non disponibles sur WhatsApp ;
- moteur bulk sans Celery ni Redis ;
- file d'attente basée sur PostgreSQL ;
- worker Django dédié via `manage.py`;
- suivi des statuts de campagne et des destinataires ;
- intégration HighLevel Conversation Provider ;
- apparition des messages sortants dans l'historique de Conversations GHL ;
- webhooks Evolution API pour `MESSAGES_UPSERT` et `CONNECTION_UPDATE`.

---

# 2. Stack technique

## Backend

- Python 3.14.x en environnement de développement actuel
- Django 5.2.x
- Django REST Framework
- PostgreSQL
- Psycopg 3
- Requests
- python-dotenv
- pycryptodome

## Frontend embarqué

- Django Templates
- Tailwind CSS via CDN
- JavaScript Vanilla
- HighLevel Custom Page / iframe

## WhatsApp

- Evolution API v2.3.7
- Integration `WHATSAPP-BAILEYS`

## Infrastructure de développement

- Django development server
- PostgreSQL local
- ngrok pour exposer Django à HighLevel
- Worker bulk via Django Management Command

Aucun Celery / Redis n'est nécessaire dans l'architecture actuelle.

---

# 3. Architecture générale

```text
                         HIGHLEVEL
                            │
              ┌─────────────┴─────────────┐
              │                           │
         Custom Page                Conversations
              │                           │
              │                    Conversation Provider
              │                           │
              ▼                           ▼
                          DJANGO
              │                           │
              │                           │
        GHL REST API                Provider Delivery URL
              │                           │
              └────────────┬──────────────┘
                           │
                           ▼
                     PostgreSQL
                           │
                  Django Bulk Worker
                           │
                           ▼
                     Evolution API
                           │
                           ▼
                        WhatsApp
```

---

# 4. Flux d'installation

Lorsqu'un utilisateur installe l'application depuis HighLevel :

```text
HighLevel Marketplace
        │
        ▼
OAuth Authorization Code
        │
        ▼
Django OAuth Callback
        │
        ▼
GHLInstallation
        │
        ▼
Création / récupération
EvolutionInstance
```

Les tokens OAuth sont stockés dans PostgreSQL.

Le backend gère également le refresh token HighLevel automatiquement.

---

# 5. Authentification de la Custom Page

La Custom Page est chargée dans un iframe HighLevel.

Le frontend demande le contexte utilisateur :

```javascript
window.parent.postMessage(
    {
        message: "REQUEST_USER_DATA",
    },
    "*"
);
```

HighLevel retourne un payload chiffré.

Django :

1. déchiffre le contexte avec le Shared Secret GHL ;
2. vérifie le `activeLocation`;
3. retrouve `GHLInstallation`;
4. génère un token interne signé et temporaire ;
5. retourne ce token au frontend.

Les appels suivants utilisent :

```http
Authorization: Bearer <embedded_token>
```

---

# 6. Modèles principaux

## GHLInstallation

Représente l'installation de l'application dans un sous-compte GHL.

Champs principaux :

- `location_id`
- `company_id`
- `user_id`
- `user_type`
- `access_token`
- `refresh_token`
- `token_type`
- `scopes`
- `expires_at`
- `is_active`

---

## EvolutionInstance

Une installation GHL possède une instance Evolution dédiée.

Champs principaux :

- `installation`
- `instance_name`
- `remote_instance_id`
- `integration`
- `instance_api_key`
- `status`
- `phone_number`
- `profile_name`
- `webhook_url`
- `webhook_secret`
- `is_active`
- `last_error`
- `metadata`
- `connected_at`
- `last_synced_at`

Statuts principaux :

```text
created
connecting
open
close
error
```

---

## BulkCampaign

Représente une campagne WhatsApp bulk.

Statuts :

```text
draft
queued
running
completed
partial
failed
cancelled
```

Champs principaux :

- `installation`
- `name`
- `message_template`
- `status`
- `created_by_highlevel_user_id`
- `total_contacts`
- `validated_count`
- `not_on_whatsapp_count`
- `validation_error_count`
- `sent_count`
- `failed_count`
- `skipped_count`
- `started_at`
- `completed_at`

---

## BulkCampaignRecipient

Un destinataire d'une campagne.

Statuts :

```text
pending
validating
ready
processing
sent
failed
skipped
not_on_whatsapp
```

Champs principaux :

- `campaign`
- `ghl_contact_id`
- `first_name`
- `last_name`
- `email`
- `phone`
- `normalized_phone`

### Vérification WhatsApp

- `is_on_whatsapp`
- `whatsapp_jid`
- `whatsapp_checked_at`
- `whatsapp_check_error`

### Envoi

- `rendered_message`
- `evolution_message_id`
- `attempts`
- `last_error`
- `sent_at`

### Synchronisation HighLevel

- `ghl_message_id`
- `ghl_conversation_id`
- `ghl_history_synced_at`
- `provider_delivery_status`

---

# 7. Custom Page

Le template principal est :

```text
apps/evolution/templates/evolution/embedded.html
```

Il contient actuellement trois espaces principaux.

## Connexion WhatsApp

Permet de :

- voir l'état de l'instance ;
- afficher le QR Code ;
- reconnecter WhatsApp ;
- afficher les informations de la location ;
- afficher le profil et le numéro connecté.

## Bulk Messages

Workflow :

```text
Sélection contacts
      ↓
Composition du message
      ↓
Création du brouillon
      ↓
Vérification WhatsApp
      ↓
Démarrage campagne
      ↓
Progression
```

Variables supportées :

```text
{{firstName}}
{{lastName}}
{{email}}
{{phone}}
```

## Campagnes

Permet de :

- consulter les campagnes ;
- voir leur statut ;
- afficher la progression ;
- consulter les compteurs ;
- reprendre une campagne en brouillon ;
- suivre une campagne active.

---

# 8. Récupération des contacts GHL

Le backend utilise l'API HighLevel Contact Search.

Endpoint interne :

```http
GET /api/ghl/embedded/contacts/
```

Paramètres :

```text
q
page
page_limit
```

Exemple :

```text
/api/ghl/embedded/contacts/?q=kevin&page=1&page_limit=25
```

Le frontend conserve les contacts sélectionnés même pendant la pagination.

Les contacts sans téléphone restent visibles mais ne peuvent pas être sélectionnés.

---

# 9. Création d'une campagne

Endpoint :

```http
POST /api/messaging/campaigns/draft/
```

Exemple de payload :

```json
{
    "name": "Promotion août",
    "message": "Bonjour {{firstName}}, bienvenue !",
    "contact_ids": [
        "contact_id_1",
        "contact_id_2"
    ],
    "confirmed_opt_in": true
}
```

Le backend ne fait pas confiance aux numéros envoyés par le navigateur.

Il reçoit uniquement les `contact_ids`, puis récupère lui-même les contacts via l'API HighLevel.

---

# 10. Vérification des numéros WhatsApp

Avant tout envoi, les numéros sont vérifiés via Evolution API.

Endpoint Evolution :

```text
POST /chat/whatsappNumbers/{instanceName}
```

Workflow :

```text
PENDING
   ↓
VALIDATING
   ↓
 ┌───────────────┐
 │               │
exists=true   exists=false
 │               │
READY      NOT_ON_WHATSAPP
```

Le champ :

```python
is_on_whatsapp
```

peut avoir :

```text
NULL   = pas encore vérifié
True   = compte WhatsApp trouvé
False  = pas disponible sur WhatsApp
```

Important :

La présence d'un JID comme :

```text
2376xxxxxxxx@s.whatsapp.net
```

ne prouve pas à elle seule que le numéro est disponible.

La source de vérité est :

```python
recipient.is_on_whatsapp is True
```

---

# 11. Endpoint de validation

```http
POST /api/messaging/campaigns/<campaign_id>/validate/
```

Exemple de réponse :

```json
{
    "success": true,
    "validation": {
        "total": 10,
        "valid": 8,
        "invalid": 2,
        "errors": 0
    }
}
```

---

# 12. Moteur bulk sans Celery / Redis

Le moteur utilise uniquement :

```text
Django
PostgreSQL
Evolution API
```

Le worker est une Django Management Command.

Structure :

```text
apps/messaging/
    management/
        __init__.py
        commands/
            __init__.py
            bulk_worker.py
```

Lancement :

```powershell
python manage.py bulk_worker
```

Le worker cherche dans PostgreSQL :

```text
campaign.status = queued/running

recipient.status = ready
recipient.is_on_whatsapp = True
```

Il réserve un destinataire avec :

```python
select_for_update(skip_locked=True)
```

puis le passe à :

```text
processing
```

---

# 13. Démarrage d'une campagne

Endpoint :

```http
POST /api/messaging/campaigns/<campaign_id>/start/
```

La campagne passe de :

```text
draft
```

à :

```text
queued
```

Le worker démarre ensuite l'envoi.

Si aucun contact `READY` n'existe, la campagne n'est pas démarrée.

---

# 14. Intervalle entre les messages

Configuration :

```env
BULK_MESSAGE_INTERVAL_SECONDS=5
```

Le worker attend entre deux traitements.

Exemple :

```text
recipient 1
   ↓
5 secondes
   ↓
recipient 2
   ↓
5 secondes
   ↓
recipient 3
```

Le délai s'exécute dans le worker et ne bloque pas une requête HTTP Django.

---

# 15. Test sur un seul destinataire

Pour traiter au maximum un recipient :

```powershell
python manage.py bulk_worker --once
```

Très utile avant de démarrer une grosse campagne.

---

# 16. Progression des campagnes

Endpoint :

```http
GET /api/messaging/campaigns/<campaign_id>/status/
```

Exemple :

```json
{
    "success": true,
    "campaign": {
        "id": 25,
        "name": "Promotion",
        "status": "running",
        "total_contacts": 10,
        "sent_count": 6,
        "failed_count": 1
    },
    "recipients": {
        "pending": 0,
        "ready": 2,
        "processing": 1,
        "sent": 6,
        "failed": 1,
        "not_on_whatsapp": 0
    }
}
```

La Custom Page effectue un polling régulier pour mettre à jour la barre de progression.

---

# 17. Liste des campagnes

Endpoint :

```http
GET /api/messaging/campaigns/
```

Affiche les campagnes appartenant à la location HighLevel active.

---

# 18. HighLevel Conversation Provider

Pour que les messages envoyés par Evolution apparaissent dans l'historique des Conversations HighLevel, l'application utilise un **Custom Conversation Provider**.

Configuration actuelle :

```text
Provider:
Evolution WhatsApp

Type:
SMS

Custom Conversation Provider:
Oui

Alias:
Evolution WhatsApp
```

Le provider doit être visible dans :

```text
HighLevel
→ Settings
→ Conversation Providers
```

Important :

Si le Conversation Provider est ajouté après que l'application a déjà été installée, il peut être nécessaire de :

```text
désinstaller l'application
puis
réinstaller l'application
```

afin d'activer le provider dans la location.

---

# 19. Flux d'envoi avec historique GHL

Le flux d'envoi final n'est pas :

```text
Worker → Evolution directement
```

Il est :

```text
Bulk Worker
     ↓
HighLevel
POST /conversations/messages
     ↓
Message créé dans Conversations GHL
     ↓
HighLevel appelle la Delivery URL
     ↓
Django Provider Endpoint
     ↓
Evolution API
     ↓
WhatsApp
```

Cela garantit que le message est d'abord connu de HighLevel.

---

# 20. Delivery URL du Conversation Provider

Endpoint :

```http
POST /api/messaging/provider/outbound/
```

Exemple avec ngrok :

```text
https://xxxxx.ngrok-free.dev/api/messaging/provider/outbound/
```

Le domaine doit correspondre au ngrok actuellement utilisé.

Si l'URL ngrok change, mettre à jour la Delivery URL dans la configuration Marketplace du Conversation Provider.

---

# 21. Signature HighLevel Provider

Les requêtes envoyées par HighLevel vers la Delivery URL sont vérifiées grâce à :

```text
X-GHL-Signature
```

La signature est vérifiée avant traitement du payload.

Fichier :

```text
apps/messaging/ghl_provider_security.py
```

---

# 22. Envoi réel via Evolution

La Delivery URL appelle :

```python
EvolutionClient.send_text(...)
```

Endpoint Evolution :

```text
POST /message/sendText/{instanceName}
```

Le numéro utilisé est :

```python
recipient.normalized_phone
```

Exemple :

```text
237620464907
```

---

# 23. Webhooks Evolution API

Les webhooks Evolution sont configurés pour :

```text
MESSAGES_UPSERT
CONNECTION_UPDATE
```

URL :

```text
/api/evolution/webhooks/<webhook_secret>/
```

Le webhook sauvegarde les événements dans PostgreSQL.

Modèle :

```text
WebhookEvent
```

Champs principaux :

- `instance`
- `event_type`
- `event_id`
- `deduplication_key`
- `payload`
- `status`
- `attempts`
- `last_error`
- `received_at`
- `processed_at`

---

# 24. Structure principale du projet

```text
ghl-evolution-connector/
│
├── apps/
│   │
│   ├── ghl/
│   │   ├── migrations/
│   │   ├── templates/
│   │   │   └── ghl/
│   │   │       └── oauth_success.html
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── client.py
│   │   ├── embedded_tokens.py
│   │   ├── models.py
│   │   ├── services.py
│   │   ├── sso.py
│   │   ├── urls.py
│   │   └── views.py
│   │
│   ├── evolution/
│   │   ├── migrations/
│   │   ├── templates/
│   │   │   └── evolution/
│   │   │       ├── dashboard.html
│   │   │       └── embedded.html
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── client.py
│   │   ├── models.py
│   │   ├── services.py
│   │   ├── urls.py
│   │   ├── webhook_urls.py
│   │   └── views.py
│   │
│   └── messaging/
│       ├── migrations/
│       ├── management/
│       │   └── commands/
│       │       └── bulk_worker.py
│       ├── admin.py
│       ├── apps.py
│       ├── ghl_provider_security.py
│       ├── models.py
│       ├── provider_views.py
│       ├── services.py
│       ├── urls.py
│       └── views.py
│
├── config/
│   ├── settings.py
│   ├── urls.py
│   └── ...
│
├── .env
├── .env.example
├── .gitignore
├── manage.py
├── requirements.txt
└── README.md
```

---

# 25. Variables d'environnement

Exemple :

```env
DEBUG=True
SECRET_KEY=change-me

DATABASE_URL=

DB_NAME=ghl_evolution
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=127.0.0.1
DB_PORT=5432

GHL_CLIENT_ID=
GHL_CLIENT_SECRET=
GHL_SHARED_SECRET=
GHL_API_VERSION=v3

GHL_CONVERSATION_PROVIDER_ID=

EVOLUTION_API_URL=https://your-evolution-domain.com
EVOLUTION_API_KEY=

APP_PUBLIC_URL=https://your-ngrok-domain.ngrok-free.dev

BULK_MESSAGE_INTERVAL_SECONDS=5
BULK_WORKER_IDLE_SECONDS=2
```

Ne jamais versionner `.env`.

---

# 26. Installation locale

## 1. Cloner le projet

```powershell
git clone <repository-url>
cd ghl-evolution-connector
```

## 2. Créer / activer l'environnement virtuel

Windows :

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## 3. Installer les dépendances

```powershell
pip install -r requirements.txt
```

## 4. Configurer `.env`

Copier :

```text
.env.example
```

vers :

```text
.env
```

puis renseigner les variables.

## 5. Migrations

```powershell
python manage.py makemigrations
python manage.py migrate
```

## 6. Vérifier Django

```powershell
python manage.py check
```

Résultat attendu :

```text
System check identified no issues
```

---

# 27. Lancer le projet en développement

Trois terminaux sont utilisés.

## Terminal 1 — Django

```powershell
cd C:\Users\dell\ghl-evolution-connector
.\.venv\Scripts\Activate.ps1

python manage.py runserver 0.0.0.0:8000
```

Ce terminal gère :

- OAuth ;
- API ;
- Custom Page ;
- campagnes ;
- validation WhatsApp ;
- Conversation Provider ;
- webhooks.

---

## Terminal 2 — Bulk Worker

```powershell
cd C:\Users\dell\ghl-evolution-connector
.\.venv\Scripts\Activate.ps1

python manage.py bulk_worker
```

Résultat :

```text
Bulk WhatsApp worker démarré.
Intervalle entre messages : 5s
```

Le worker doit rester ouvert pour traiter les campagnes.

Si le worker n'est pas actif, une campagne peut rester :

```text
queued
```

---

## Terminal 3 — ngrok

```powershell
ngrok http 8000
```

Exemple :

```text
https://xxxxx.ngrok-free.dev
    →
http://localhost:8000
```

Cette URL est utilisée par HighLevel pour :

- OAuth Redirect URL ;
- Custom Page ;
- Conversation Provider Delivery URL ;
- éventuellement autres callbacks publics.

---

# 28. Endpoints principaux

## HighLevel

```text
GET/POST OAuth
/api/ghl/oauth/callback/

/api/ghl/user-context/

/api/ghl/embedded/contacts/
```

## Evolution

```text
/evolution/embedded/

/evolution/api/embedded/status/

/api/evolution/webhooks/<secret>/
```

## Messaging

```text
GET  /api/messaging/campaigns/

POST /api/messaging/campaigns/draft/

POST /api/messaging/campaigns/<id>/validate/

POST /api/messaging/campaigns/<id>/start/

GET  /api/messaging/campaigns/<id>/status/

POST /api/messaging/provider/outbound/
```

---

# 29. Configuration Marketplace HighLevel

L'application utilise actuellement :

## OAuth

Scopes minimum utiles :

```text
contacts.readonly
contacts.write
conversations.readonly
conversations.write
conversations/message.write
```

Après ajout ou modification d'un scope, il faut généralement réinstaller l'application afin que le nouveau token OAuth reçoive ce scope.

## Custom Page

La page embarquée pointe vers :

```text
/evolution/embedded/
```

## Shared Secret

Utilisé pour déchiffrer le contexte utilisateur Custom Page.

## Conversation Provider

Alias actuel :

```text
Evolution WhatsApp
```

Type :

```text
SMS
```

Delivery URL :

```text
https://PUBLIC_DOMAIN/api/messaging/provider/outbound/
```

---

# 30. Dépannage

## WhatsApp semble connecté mais la validation retourne 502

Vérifier la page :

```text
Evolution Messaging
→ Connexion WhatsApp
```

Si un QR Code apparaît, reconnecter le compte WhatsApp.

Une instance peut rester enregistrée côté Django alors que la session WhatsApp distante est fermée.

---

## Validation réussie mais aucun message n'est envoyé

Vérifier le worker :

```powershell
python manage.py bulk_worker
```

Sans worker, les campagnes restent dans la file.

---

## Le worker affiche `failed`

Vérifier :

```python
recipient.last_error
```

Exemple :

```powershell
python manage.py shell
```

```python
from apps.messaging.models import BulkCampaign

campaign = BulkCampaign.objects.get(pk=19)

for r in campaign.recipients.all():
    print(
        r.id,
        r.status,
        r.last_error,
    )
```

---

## HighLevel retourne HTTP 404 lors de l'envoi Provider

Vérifier que :

1. le Conversation Provider est bien créé ;
2. `GHL_CONVERSATION_PROVIDER_ID` est correct ;
3. le provider apparaît dans :

```text
Settings
→ Conversation Providers
```

4. l'application a été réinstallée après création du provider.

---

## Provider installé mais Delivery URL non appelée

Vérifier :

- ngrok ;
- Delivery URL Marketplace ;
- URL publique actuelle ;
- scope `conversations/message.write`;
- logs Django.

---

## Après réinstallation GHL, WhatsApp ne fonctionne plus

La réinstallation GHL et la session WhatsApp Evolution sont deux mécanismes différents.

Si nécessaire :

```text
Evolution Messaging
→ Connexion WhatsApp
→ Scanner le QR Code
```

---

# 31. Notes de sécurité

L'état actuel du projet est orienté développement.

Avant production :

- chiffrer les tokens sensibles au repos ;
- sécuriser les secrets Evolution ;
- utiliser HTTPS permanent ;
- remplacer ngrok par un domaine stable ;
- utiliser Gunicorn/Uvicorn derrière Nginx ;
- isoler PostgreSQL ;
- lancer `bulk_worker` comme service systemd ;
- limiter et monitorer les volumes bulk ;
- ajouter des logs structurés ;
- mettre en place des retries contrôlés ;
- ajouter une stratégie d'idempotence complète ;
- respecter les règles d'opt-in des destinataires ;
- éviter les campagnes non sollicitées.

---

# 32. Déploiement cible

Sur un VPS Linux :

```text
Nginx
   │
   ▼
Django Web Service

PostgreSQL

Django Bulk Worker Service

Evolution API
```

Exemple services :

```text
ghl-evolution-web.service
ghl-evolution-bulk-worker.service
```

Le worker peut être lancé avec :

```bash
python manage.py bulk_worker
```

---

# 33. Roadmap

Fonctionnalités prévues / prochaines étapes :

- synchronisation inbound Evolution → HighLevel Conversations ;
- affichage des réponses WhatsApp dans GHL ;
- action rapide depuis une fiche Contact GHL ;
- bulk action directement depuis la Smart List / Contacts ;
- pause campagne ;
- reprise campagne ;
- annulation campagne ;
- relance sélective des échecs ;
- détail des destinataires ;
- statistiques avancées ;
- templates de messages ;
- historique d'envois par contact ;
- gestion de pièces jointes ;
- statut de livraison / lecture ;
- logs administrateur ;
- système de permissions par rôle ;
- domaine public stable ;
- déploiement production.

---

# 34. Etat actuel

À ce stade, le projet permet déjà de réaliser le workflow suivant :

```text
Installation GHL
       ↓
Connexion WhatsApp QR
       ↓
Contacts GHL
       ↓
Sélection
       ↓
Création campagne
       ↓
Vérification WhatsApp
       ↓
Filtrage des numéros
       ↓
Démarrage
       ↓
Worker PostgreSQL
       ↓
HighLevel Conversation Provider
       ↓
Evolution API
       ↓
WhatsApp
       ↓
Suivi SENT / FAILED
       ↓
Historique GHL
```

Le projet est donc déjà exploitable comme base fonctionnelle d'un connecteur WhatsApp Marketplace pour HighLevel.

---

## Licence

À définir selon les besoins du projet.

## Auteur

Projet développé dans le cadre du connecteur **Evolution Messaging / HighLevel + Evolution API**.

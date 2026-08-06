# GHL Evolution Connector

Backend Django permettant de connecter un sous-compte **GoHighLevel** à une instance **Evolution API** afin de préparer l'envoi et la réception de messages WhatsApp directement depuis HighLevel.

Le projet est conçu comme une application Marketplace HighLevel multi-tenant : chaque sous-compte HighLevel possède sa propre installation OAuth et sa propre instance Evolution API.

---

## Sommaire

- [Objectif du projet](#objectif-du-projet)
- [Fonctionnalités déjà implémentées](#fonctionnalités-déjà-implémentées)
- [Architecture générale](#architecture-générale)
- [Stack technique](#stack-technique)
- [Structure du projet](#structure-du-projet)
- [Prérequis](#prérequis)
- [Installation locale](#installation-locale)
- [Configuration PostgreSQL](#configuration-postgresql)
- [Variables d'environnement](#variables-denvironnement)
- [Migrations](#migrations)
- [Lancement du serveur](#lancement-du-serveur)
- [Configuration GoHighLevel](#configuration-gohighlevel)
- [Configuration Evolution API](#configuration-evolution-api)
- [Flux OAuth](#flux-oauth)
- [Création d'une instance Evolution](#création-dune-instance-evolution)
- [Dashboard QR Code](#dashboard-qr-code)
- [Endpoints disponibles](#endpoints-disponibles)
- [Modèles de données](#modèles-de-données)
- [Sécurité](#sécurité)
- [Dépannage](#dépannage)
- [Workflow Git](#workflow-git)
- [Feuille de route](#feuille-de-route)
- [Licence](#licence)

---

## Objectif du projet

Le but est de permettre à un utilisateur HighLevel de :

1. installer l'application dans un sous-compte ;
2. autoriser le backend via OAuth 2.0 ;
3. créer automatiquement une instance Evolution API dédiée ;
4. afficher un QR Code de connexion WhatsApp ;
5. connecter un numéro WhatsApp ;
6. envoyer des messages WhatsApp depuis HighLevel ;
7. recevoir les messages WhatsApp dans les conversations HighLevel.

Architecture logique :

```text
GoHighLevel Sub-Account
        |
        | OAuth 2.0
        v
Backend Django
        |
        | API REST
        v
Evolution API
        |
        v
WhatsApp
```

Chaque sous-compte HighLevel est isolé :

```text
Agency HighLevel
|
+-- Location A -> Installation OAuth A -> Instance Evolution A
+-- Location B -> Installation OAuth B -> Instance Evolution B
+-- Location C -> Installation OAuth C -> Instance Evolution C
```

---

## Fonctionnalités déjà implémentées

### HighLevel

- création d'une application Marketplace privée ;
- ciblage des sous-comptes HighLevel ;
- OAuth 2.0 Authorization Code ;
- récupération du `location_id` ;
- stockage de l'Access Token et du Refresh Token ;
- rafraîchissement automatique des tokens ;
- protection contre les doubles rafraîchissements avec verrou PostgreSQL ;
- endpoint de callback OAuth ;
- endpoint de santé du service.

### Evolution API

- configuration du serveur Evolution API ;
- test de connexion au serveur ;
- création d'une instance WhatsApp ;
- association d'une instance Evolution à une installation HighLevel ;
- récupération de l'état de connexion ;
- récupération du QR Code ;
- réutilisation d'une instance déjà existante ;
- stockage local des informations importantes de l'instance.

### Interface Django

- dashboard de connexion WhatsApp ;
- interface Tailwind CSS via CDN ;
- affichage du statut de connexion ;
- affichage du QR Code ;
- actualisation automatique toutes les 10 secondes ;
- bouton d'actualisation manuel ;
- affichage des erreurs Evolution API ;
- protection temporaire avec un compte administrateur Django.

---

## Architecture générale

```text
Utilisateur HighLevel
        |
        | Installe l'application
        v
GoHighLevel OAuth
        |
        | code OAuth
        v
Django Callback
        |
        | échange du code
        v
HighLevel Token Endpoint
        |
        | access_token + refresh_token + location_id
        v
PostgreSQL
        |
        | provisionnement
        v
Evolution API
        |
        | QR Code
        v
Dashboard Django
```

Flux futur des messages entrants :

```text
WhatsApp
   |
   v
Evolution API Webhook
   |
   v
Django
   |
   +--> Upsert du contact dans HighLevel
   |
   +--> Injection du message dans la conversation HighLevel
```

Flux futur des messages sortants :

```text
Workflow HighLevel
   |
   v
Custom Workflow Action
   |
   v
Django
   |
   v
Evolution API
   |
   v
WhatsApp
```

---

## Stack technique

- Python 3.11+
- Django 5.2
- Django REST Framework
- PostgreSQL
- Psycopg 3
- Requests
- python-dotenv
- Tailwind CSS via CDN
- GoHighLevel API
- Evolution API
- ngrok pour le développement local HTTPS

Prévu pour la suite :

- Celery
- Redis
- chiffrement des secrets
- webhooks asynchrones
- déploiement Docker

---

## Structure du projet

```text
ghl-evolution-connector/
|
+-- apps/
|   |
|   +-- ghl/
|   |   +-- migrations/
|   |   +-- admin.py
|   |   +-- apps.py
|   |   +-- models.py
|   |   +-- services.py
|   |   +-- urls.py
|   |   +-- views.py
|   |
|   +-- evolution/
|       +-- migrations/
|       +-- templates/
|       |   +-- evolution/
|       |       +-- dashboard.html
|       +-- admin.py
|       +-- apps.py
|       +-- client.py
|       +-- models.py
|       +-- services.py
|       +-- urls.py
|       +-- views.py
|
+-- config/
|   +-- settings.py
|   +-- urls.py
|   +-- asgi.py
|   +-- wsgi.py
|
+-- .env
+-- .env.example
+-- .gitignore
+-- manage.py
+-- requirements.txt
+-- README.md
```

---

## Prérequis

Avant de commencer, installer :

- Python 3.11 ou plus récent ;
- PostgreSQL ;
- Git ;
- un éditeur de code comme VS Code ;
- ngrok pour le développement OAuth local ;
- accès à un serveur Evolution API ;
- un compte développeur HighLevel Marketplace ;
- un compte Sandbox HighLevel avec au moins un sous-compte de test.

Vérifications :

```powershell
python --version
git --version
psql --version
```

---

## Installation locale

### 1. Cloner le dépôt

```powershell
git clone https://github.com/VOTRE_UTILISATEUR/ghl-evolution-connector.git
cd ghl-evolution-connector
```

### 2. Créer l'environnement virtuel

Sous Windows PowerShell :

```powershell
py -3.11 -m venv .venv
```

Activation :

```powershell
.\.venv\Scripts\Activate.ps1
```

Si PowerShell bloque l'activation :

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 3. Installer les dépendances

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## Configuration PostgreSQL

Ouvrir pgAdmin ou `psql`, puis créer un utilisateur et une base :

```sql
CREATE USER ghl_app WITH PASSWORD 'REMPLACEZ_PAR_UN_MOT_DE_PASSE_FORT';

CREATE DATABASE ghl_whatsapp_db
    OWNER ghl_app
    ENCODING 'UTF8';
```

Vérification :

```sql
SELECT datname
FROM pg_database
WHERE datname = 'ghl_whatsapp_db';
```

---

## Variables d'environnement

Copier le fichier d'exemple :

```powershell
Copy-Item .env.example .env
```

Exemple de `.env` :

```env
DJANGO_SECRET_KEY=change-me
DJANGO_DEBUG=True

DB_NAME=ghl_whatsapp_db
DB_USER=ghl_app
DB_PASSWORD=change-me
DB_HOST=127.0.0.1
DB_PORT=5432

GHL_CLIENT_ID=your-client-id
GHL_CLIENT_SECRET=change-me
GHL_REDIRECT_URI=https://your-ngrok-domain.ngrok-free.app/api/ghl/oauth/callback/
GHL_API_VERSION=v3

EVOLUTION_API_URL=https://your-evolution-domain.com
EVOLUTION_API_KEY=change-me
EVOLUTION_INTEGRATION=WHATSAPP-BAILEYS
```

Générer une clé secrète Django :

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Important :

- ne jamais envoyer `.env` sur GitHub ;
- ne jamais partager le `GHL_CLIENT_SECRET` ;
- ne jamais partager `EVOLUTION_API_KEY` ;
- ne jamais afficher les Access Tokens ou Refresh Tokens dans les logs.

---

## Migrations

Créer ou appliquer les migrations :

```powershell
python manage.py makemigrations
python manage.py migrate
```

Vérifier la configuration :

```powershell
python manage.py check
```

---

## Lancement du serveur

```powershell
python manage.py runserver 0.0.0.0:8000
```

Serveur local :

```text
http://127.0.0.1:8000/
```

Endpoint de santé :

```text
http://127.0.0.1:8000/api/ghl/health/
```

Réponse attendue :

```json
{
  "status": "ok",
  "service": "ghl-evolution-connector"
}
```

---

## Configuration GoHighLevel

### Application Marketplace

Configuration recommandée :

```text
App Type: Private
Target User: Sub-Account
Who can install: Everyone
Bulk installation: No
Listing type: Standard
```

### Scopes OAuth actuels

```text
contacts.write
conversations/message.write
```

Ces scopes serviront à :

- créer ou mettre à jour des contacts HighLevel ;
- injecter les messages entrants dans les conversations HighLevel.

### URL de redirection OAuth

Pendant le développement local :

```text
https://VOTRE_DOMAINE_NGROK.ngrok-free.app/api/ghl/oauth/callback/
```

La valeur doit être identique dans :

- HighLevel Marketplace ;
- le fichier `.env` ;
- le service OAuth Django.

---

## Flux OAuth

### 1. Exposer Django avec ngrok

Premier terminal :

```powershell
python manage.py runserver 0.0.0.0:8000
```

Deuxième terminal :

```powershell
ngrok http 8000
```

### 2. Ouvrir le Test Link HighLevel

Le Test Link ouvre la page d'installation de l'application.

Après validation :

```text
HighLevel
-> Redirect URL
-> /api/ghl/oauth/callback/?code=...
```

### 3. Échange du code OAuth

Django envoie le code vers le endpoint OAuth HighLevel avec un corps :

```text
application/x-www-form-urlencoded
```

Le backend sauvegarde ensuite :

- `location_id` ;
- `company_id` ;
- `user_id` ;
- `access_token` ;
- `refresh_token` ;
- `expires_at` ;
- `scope` ;
- `user_type`.

### 4. Rafraîchissement automatique

Avant un futur appel à l'API HighLevel :

```python
from apps.ghl.services import get_valid_access_token

access_token = get_valid_access_token(installation.pk)
```

Le service :

1. vérifie l'expiration ;
2. rafraîchit le token s'il expire bientôt ;
3. sauvegarde le nouvel Access Token ;
4. sauvegarde le nouveau Refresh Token ;
5. évite deux rafraîchissements simultanés avec `select_for_update()`.

---

## Configuration Evolution API

Ajouter les paramètres suivants dans `.env` :

```env
EVOLUTION_API_URL=https://your-evolution-domain.com
EVOLUTION_API_KEY=change-me
EVOLUTION_INTEGRATION=WHATSAPP-BAILEYS
```

Tester la connexion dans le shell Django :

```powershell
python manage.py shell
```

```python
import requests
from django.conf import settings

response = requests.get(
    f"{settings.EVOLUTION_API_URL}/instance/fetchInstances",
    headers={
        "apikey": settings.EVOLUTION_API_KEY,
        "Accept": "application/json",
    },
    timeout=30,
)

print(response.status_code)
print(response.text[:1000])
```

Résultat attendu :

```text
200
```

---

## Création d'une instance Evolution

Le service principal est :

```python
from apps.evolution.services import provision_evolution_instance
```

Exemple :

```python
from apps.ghl.models import GHLInstallation
from apps.evolution.services import provision_evolution_instance

installation = GHLInstallation.objects.first()

instance, created = provision_evolution_instance(
    installation
)

print(instance.instance_name)
print(instance.status)
print(created)
```

Nom généré :

```text
ghl-{location_id}
```

Exemple :

```text
ghl-93dZ8qhAsglT9n60WDJe
```

Le service ne recrée pas une instance déjà présente dans PostgreSQL.

Comportement :

```text
Installation existante
|
+-- EvolutionInstance existe -> réutilisation
|
+-- EvolutionInstance absente -> POST /instance/create
```

---

## Dashboard QR Code

URL locale :

```text
http://127.0.0.1:8000/evolution/dashboard/VOTRE_LOCATION_ID/
```

Exemple :

```text
http://127.0.0.1:8000/evolution/dashboard/93dZ8qhAsglT9n60WDJe/
```

La page affiche :

- le statut de l'instance ;
- le QR Code ;
- le nom de l'instance ;
- le Location ID ;
- le type d'intégration ;
- la dernière vérification ;
- les erreurs éventuelles.

Le statut est actualisé automatiquement toutes les 10 secondes.

### Protection actuelle

Le dashboard utilise temporairement :

```python
@staff_member_required
```

Il faut donc créer un administrateur Django :

```powershell
python manage.py createsuperuser
```

Cette protection sera remplacée plus tard par une authentification compatible avec l'Iframe HighLevel.

---

## Endpoints disponibles

### Santé du backend

```http
GET /api/ghl/health/
```

### Callback OAuth HighLevel

```http
GET /api/ghl/oauth/callback/?code=...
```

### Dashboard WhatsApp

```http
GET /evolution/dashboard/<location_id>/
```

### Statut JSON de l'instance

```http
GET /evolution/api/status/<location_id>/
```

Exemple de réponse :

```json
{
  "success": true,
  "status": "connecting",
  "is_connected": false,
  "qr_source": "data:image/png;base64,...",
  "qr_count": 10,
  "pairing_code": null,
  "phone_number": "",
  "profile_name": "",
  "last_synced_at": "2026-08-05T13:30:00Z"
}
```

---

## Modèles de données

### GHLInstallation

Représente l'installation OAuth d'un sous-compte HighLevel.

Principaux champs :

```text
location_id
company_id
user_id
user_type
access_token
refresh_token
token_type
scopes
expires_at
is_active
installed_at
updated_at
```

Relation :

```text
1 GHLInstallation
        |
        | OneToOne
        v
1 EvolutionInstance
```

### EvolutionInstance

Représente une session WhatsApp sur Evolution API.

Principaux champs :

```text
installation
instance_name
remote_instance_id
integration
instance_api_key
status
phone_number
profile_name
webhook_url
is_active
last_error
metadata
connected_at
last_synced_at
created_at
updated_at
```

Statuts internes :

```text
created
connecting
open
close
error
```

---

## Sécurité

Mesures déjà appliquées :

- `.env` exclu de Git ;
- tokens non affichés dans les pages ;
- clés sensibles masquées dans Django Admin ;
- rafraîchissement transactionnel ;
- timeout sur les requêtes HTTP ;
- validation des réponses externes ;
- instance unique par installation HighLevel.

Mesures à ajouter avant la production :

- chiffrement des tokens OAuth en base ;
- chiffrement des clés Evolution ;
- HTTPS permanent ;
- validation des signatures de webhooks ;
- protection contre les rejeux ;
- journal d'audit ;
- limitation de débit ;
- politique CORS et CSP ;
- remplacement du CDN Tailwind par une compilation locale ;
- serveur WSGI ou ASGI de production ;
- `DEBUG=False` ;
- rotation régulière des secrets ;
- stockage des secrets dans un gestionnaire sécurisé.

---

## Dépannage

### Erreur OAuth : `content must be application/x-www-form-urlencoded`

Cause :

```text
Le payload OAuth a été envoyé en JSON.
```

Correction :

```python
response = requests.post(
    url,
    data=payload,
    headers=headers,
)
```

Ne pas utiliser :

```python
json=payload
```

---

### Erreur Evolution : HTTP 401 ou 403

Causes possibles :

- clé API globale incorrecte ;
- mauvaise URL Evolution API ;
- tentative de création d'une instance déjà existante ;
- permissions du serveur ;
- instance désactivée.

Vérifier :

```env
EVOLUTION_API_URL=
EVOLUTION_API_KEY=
```

---

### Le dashboard essaie de recréer une instance

Le service doit réutiliser l'instance locale existante :

```python
if existing_instance:
    return existing_instance, False
```

Un statut `error` ne signifie pas que l'instance distante doit être recréée.

---

### `Not Found: /favicon.ico`

Ce message n'empêche pas le fonctionnement du projet.

Le navigateur cherche simplement une icône de site.

---

### Le QR Code ne s'affiche pas

Vérifier :

1. l'instance existe dans Evolution Manager ;
2. l'instance n'est pas déjà connectée ;
3. `GET /instance/connect/{instance_name}` retourne `base64` ;
4. la clé API est correcte ;
5. le serveur Evolution est accessible.

---

### Le callback OAuth retourne `code absent`

Cette réponse est normale lorsque l'URL est ouverte directement :

```json
{
  "status": "error",
  "message": "Le paramètre OAuth 'code' est absent."
}
```

Le paramètre `code` est envoyé uniquement après l'installation HighLevel.

---

### Le domaine ngrok change

Avec une URL ngrok temporaire, mettre à jour :

```env
GHL_REDIRECT_URI=
```

et la Redirect URL dans le portail HighLevel.

Les deux valeurs doivent être strictement identiques.

---

## Workflow Git

Vérifier les fichiers :

```powershell
git status
```

Ajouter les modifications :

```powershell
git add .
```

Créer un commit :

```powershell
git commit -m "feat: add Evolution WhatsApp QR dashboard"
```

Envoyer sur GitHub :

```powershell
git push origin main
```

Vérifier que ces fichiers ne sont pas suivis :

```text
.env
.venv/
__pycache__/
```

Vérification :

```powershell
git check-ignore -v .env
```

---

## Feuille de route

### Phase 1 — Fondation

- [x] projet Django ;
- [x] PostgreSQL ;
- [x] application Marketplace privée ;
- [x] compte Sandbox ;
- [x] OAuth HighLevel ;
- [x] stockage des installations ;
- [x] rafraîchissement des tokens ;
- [x] connexion Evolution API ;
- [x] création d'instance Evolution ;
- [x] affichage du QR Code ;
- [x] dashboard Tailwind.

### Phase 2 — Intégration HighLevel

- [ ] authentification du Custom Menu Link ;
- [ ] Iframe HighLevel ;
- [ ] association automatique de l'instance après OAuth ;
- [ ] récupération du profil et du numéro WhatsApp ;
- [ ] écran de déconnexion et reconnexion ;
- [ ] gestion de la désinstallation HighLevel.

### Phase 3 — Messages entrants

- [ ] webhook Evolution API ;
- [ ] événement `MESSAGES_UPSERT` ;
- [ ] idempotence des webhooks ;
- [ ] normalisation des numéros ;
- [ ] création ou mise à jour des contacts HighLevel ;
- [ ] injection dans les conversations HighLevel ;
- [ ] journalisation des messages.

### Phase 4 — Messages sortants

- [ ] Custom Workflow Action HighLevel ;
- [ ] endpoint Django d'envoi ;
- [ ] appel `sendText` Evolution API ;
- [ ] gestion des erreurs et retries ;
- [ ] suivi des statuts de livraison.

### Phase 5 — Production

- [ ] Celery ;
- [ ] Redis ;
- [ ] Docker ;
- [ ] chiffrement des secrets ;
- [ ] monitoring ;
- [ ] tests unitaires et d'intégration ;
- [ ] documentation API ;
- [ ] CI/CD GitHub Actions ;
- [ ] déploiement HTTPS ;
- [ ] politique de confidentialité ;
- [ ] conditions d'utilisation ;
- [ ] soumission publique au Marketplace.

---

## Commandes utiles

### Lancer Django

```powershell
python manage.py runserver
```

### Vérifier le projet

```powershell
python manage.py check
```

### Ouvrir le shell

```powershell
python manage.py shell
```

### Appliquer les migrations

```powershell
python manage.py migrate
```

### Créer un administrateur

```powershell
python manage.py createsuperuser
```

### Générer les dépendances

```powershell
python -m pip freeze > requirements.txt
```

### Lancer ngrok

```powershell
ngrok http 8000
```

---

## Bonnes pratiques de contribution

Créer une branche par fonctionnalité :

```powershell
git checkout -b feature/evolution-webhooks
```

Commits recommandés :

```text
feat: nouvelle fonctionnalité
fix: correction de bug
docs: documentation
refactor: restructuration du code
test: ajout de tests
chore: maintenance
```

Exemple :

```powershell
git commit -m "docs: complete project README"
```

---

## Licence

Le projet est actuellement privé.

Ajouter une licence uniquement lorsque les conditions de distribution du projet auront été définies.

---

## Statut du projet

```text
Version actuelle : prototype fonctionnel
OAuth HighLevel : opérationnel
PostgreSQL : opérationnel
Evolution API : opérationnel
Création d'instance : opérationnelle
QR Code : opérationnel
Messagerie bidirectionnelle : à implémenter
Production : non prête
```

# Docker usage

## Build

```bash
docker build -t ghl-evolution-connector .
```

## Web container

```bash
docker run -d \
  --name ghl-evolution-web \
  --env-file .env \
  -e APP_MODE=web \
  -p 8000:8000 \
  -v ghl-evolution-media:/app/media \
  ghl-evolution-connector
```

`APP_MODE=web` lance les migrations puis Gunicorn.

## Bulk worker

Utiliser la MEME image :

```bash
docker run -d \
  --name ghl-evolution-worker \
  --env-file .env \
  -e APP_MODE=worker \
  -v ghl-evolution-media:/app/media \
  ghl-evolution-connector
```

`APP_MODE=worker` lance :

```text
python manage.py bulk_worker
```

## PostgreSQL

Les deux conteneurs doivent utiliser la meme base PostgreSQL.

Dans un conteneur, `127.0.0.1` designe le conteneur lui-meme.
Utiliser donc le nom DNS du service PostgreSQL ou l'URL fournie par l'hebergeur.

## Media

Les fichiers de campagne sont stockes dans `/app/media`.
Ce dossier doit etre persistant et partage si necessaire.

Pour la production, exposer `/media/` via Nginx/Caddy ou utiliser
un stockage objet compatible S3. Evolution API doit pouvoir acceder
publiquement aux URLs des fichiers.

## Variables importantes

```env
DEBUG=False
APP_PUBLIC_URL=https://votre-domaine.com
PORT=8000
WEB_CONCURRENCY=3
GUNICORN_TIMEOUT=120
```

Le serveur Django `runserver` ne doit pas etre utilise en production.

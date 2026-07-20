# NFL Pick'em

A Progressive Web App for running NFL pick'em leagues, with live score updates and a mobile-first interface.

Pick one game each week, follow the league rules, and climb the standings. Self-hosted, no accounts on anyone else's servers, no wagering.

## Features

- **Weekly picks** — select one team per week to win; change your pick any time before that game kicks off
- **League rules** — each team usable only once per regular season, and no picking against the same opponent two weeks running (both configurable per group)
- **Groups** — create or join unlimited leagues, with per-group rule sets and picks
- **Playoffs** — regular-season standings are frozen after Week 18; the top finishers advance to a separate playoff and Super Bowl bracket
- **Scoring** — 1 point for a win, 0.5 for a tie, 0 for a loss; ties broken on margin of victory
- **Real-time updates** — live scores pushed over WebSockets
- **PWA** — installable on any device, with offline caching
- **Admin tools** — manage picks on behalf of members, audit log, scheduler controls

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Git

### Using pre-built images (recommended)

```bash
git clone https://github.com/crazynudelsieb/nfl_pickem.git
cd nfl_pickem

# Copy the sample environment and generate secrets
cp .env.example .env
python generate_secrets.py

docker compose up -d
# Access at http://localhost:5000
```

### Building locally

```bash
docker compose -f docker-compose.local.yml up --build -d
```

### First season setup

```bash
# Create the season and pull teams + schedule from the upstream NFL data feed
docker compose exec web python manage.py season create 2026 --activate
docker compose exec web python manage.py sync all 2026
```

### Create an admin user

```bash
docker compose exec web python manage.py user create-admin USERNAME EMAIL PASSWORD
```

## Configuration

All settings are read from `.env` — see [.env.example](.env.example) for the full annotated list. The essentials:

```env
FLASK_ENV=production
SECRET_KEY=<generate with generate_secrets.py>
WTF_CSRF_SECRET_KEY=<generate with generate_secrets.py>
DATABASE_URL=postgresql://user:pass@db:5432/nfl_pickem
TIMEZONE=Europe/Vienna
```

Contact links, the commercial-license address, and the optional Impressum page are all driven by the `CONTACT_*` and `IMPRINT_*` variables. Every one is opt-in: leave it blank and it simply never appears. `/impressum` is served only once `IMPRINT_NAME` is set.

## Building images

A multi-architecture image (`linux/amd64` + `linux/arm64`) is published to GHCR.

**Locally** (requires a `multiarch-builder` buildx builder with QEMU):

```powershell
docker buildx create --name multiarch-builder --driver docker-container --use
docker buildx inspect multiarch-builder --bootstrap

./build.ps1
```

**Via CI** — the [Build Multi-Arch Images](.github/workflows/build-multiarch.yml) workflow runs on any `v*` tag, or on demand from the Actions tab:

```bash
git tag v1.2.35
git push origin v1.2.35
```

Manual runs accept an optional version tag and let you toggle `:latest` and `--no-cache`.

## Technology Stack

**Backend**: Python 3.12+, Flask, SQLAlchemy, PostgreSQL
**Frontend**: Jinja2, vanilla JS, custom CSS, Socket.IO
**Infrastructure**: Docker, Gunicorn, reverse proxy (Nginx recommended)
**Background jobs**: APScheduler with adaptive sync frequency

## Project Structure

```
app/
├── models/          # Database models (User, Pick, Game, Season, Team, Group)
├── routes/          # Page & API routes (auth, main, groups, api)
├── services/        # Background services (scheduler_service)
├── static/          # CSS, JS, PWA assets (manifest.json, sw.js)
├── templates/       # Jinja2 templates (base, main, auth, groups, legal, errors)
└── utils/           # Helpers (scoring, data_sync, cache_utils, leaderboard)
```

### Key files

- **`app/models/pick.py`** — pick validation and result scoring (`is_valid_pick()`, `update_result()`)
- **`app/models/user.py`** — rule checks and season stats (`can_pick_team()`, `get_season_stats()`)
- **`app/models/group.py`** — per-group rule configuration (`rules_for()`, `DEFAULT_RULES`)
- **`app/utils/scoring.py`** — individual pick scoring (`calculate_pick_score()`)
- **`app/utils/leaderboard.py`** — leaderboard assembly and ordering
- **`app/services/scheduler_service.py`** — background data sync
- **`config.py`** — environment-specific configuration classes

## Management CLI

```bash
python manage.py season create 2026 --activate   # Create and activate a season
python manage.py sync all 2026                   # Sync teams + schedule
python manage.py sync scores                     # Update live scores
python manage.py user create-admin USER EMAIL PW # Create an admin
python manage.py status                          # Application health
```

## API Endpoints

```
GET  /api/seasons/current         # Current season data
GET  /api/groups/<id>/leaderboard # Group standings
GET  /api/picks                   # User picks with filters
POST /picks/make/<game_id>        # Submit pick
```

## Production Deployment

1. **Server**: Ubuntu 22.04+, 2 GB RAM, Docker installed
2. **Configure**: set production values in `.env` (never commit it)
3. **Deploy**: `docker compose up -d`
4. **Proxy**: put Nginx in front with TLS
5. **Monitor**: `docker compose logs -f web`

### Nginx example

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## Development

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

export FLASK_ENV=development
python run.py             # http://localhost:5000
```

SQLite is used automatically when PostgreSQL isn't reachable in development. Caching and rate limiting are always in-process - the app runs as a single worker, so there is no cache server to run.

### Database schema

The schema is created on startup with `db.create_all()`, which only ever creates *missing tables* — it will not add a column to a table that already exists. Versioned Alembic migrations are not in use yet.

So when you add a column to an existing model, also register it in [`app/utils/schema_guard.py`](app/utils/schema_guard.py). The guard applies the missing columns with an idempotent `ALTER TABLE` at startup, on both PostgreSQL and SQLite. Skipping this step is the usual cause of an `UndefinedColumn` error after deploying a model change to an existing database.

## Security

- Generate secrets with `python generate_secrets.py` — never ship the defaults
- Never commit a `.env` containing real credentials
- Serve over HTTPS in production
- Keep dependencies and base images patched

Vulnerability reports: please use [private security advisories](https://github.com/crazynudelsieb/nfl_pickem/security/advisories/new) rather than public issues. See [SECURITY.md](SECURITY.md).

## Disclaimer

This project is not affiliated with, endorsed by, or sponsored by the National Football League. NFL team names and logos are the property of their respective owners. Schedules and scores come from a public third-party feed and may be delayed or incomplete — the official NFL result always governs. The app is for entertainment among friends: it involves no wagering, stakes, or prizes.

## License

NFL Pick'em is **source-available, not open source**. Personal and noncommercial use — including self-hosting — is free under the **PolyForm Noncommercial License 1.0.0**; see [LICENSE](LICENSE).

Commercial use requires a separate license: appchen@outlook.at

## Contributing

Bug reports and feature requests are welcome via [GitHub Issues](https://github.com/crazynudelsieb/nfl_pickem/issues). For code changes, fork the repository, create a feature branch, and open a pull request.

See [CHANGELOG.md](CHANGELOG.md) for version history.

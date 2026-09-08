# NFL Pick'em

A Progressive Web App for running NFL pick'em leagues, with live score updates and a mobile-first interface.

Pick one game each week, follow the league rules, and climb the standings. Self-hosted, no accounts on anyone else's servers, no wagering.

Part of the appchen ecosystem: [appchen.com](https://appchen.com) is the main hub for all -chen apps.

## appchen ecosystem

[appchen.com](https://appchen.com) is the hub for the -chen apps: small, privacy-first
web apps, most of them usable without an account. The hub carries each app's current
maturity (alpha / beta / stable); the list below is just what they are.

| App | What it does |
| --- | --- |
| [splittchen](https://splittchen.com) | Split group expenses and settle up - no registration, no accounts |
| [konsumchen](https://konsumchen.com) | Log a drink or a dose in two taps and see your real trends over time |
| [terminchen](https://terminchen.com) | A shared calendar for friend groups and clubs - just a link, no accounts |
| [festivalplaylist](https://festivalplaylist.com) | Auto-generated Spotify & YouTube Music playlists for festival lineups |
| [streamchen](https://streamchen.com) | Collaborative radio: one shared live stream, queue, voting, no accounts |
| [chefchen](https://chefchen.appchen.com) | A weekly cooking planner with ingredient and recipe suggestions |
| [kaloriechen](https://kaloriechen.appchen.com) | A lightweight calorie tracker built for fast logging and simple daily totals |
| [fitquest](https://fitquest.appchen.com) | Turn your training plan into small quests and keep motivation high |
| **NFL Pick'em** (this project) | Weekly NFL pick'em leagues - live at [pickem.appchen.com](https://pickem.appchen.com) |

Each app is linked to where you can actually use it. This project is the only one whose
source is public, so it is the only GitHub link here:
[nfl_pickem](https://github.com/crazynudelsieb/nfl_pickem).

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
# Creates the season row and pulls teams + schedule from the upstream NFL data feed
docker compose exec web python manage.py sync all 2026

# Make it the season the app serves
docker compose exec web python manage.py season activate 2026
```

`sync all` creates the season if it does not exist yet, so it is the only bootstrap step
needed. Sync before activating - activating first would point the app at a season with no
teams and no games.

**Later seasons roll over on their own.** From August 1st the daily maintenance job
(`_ensure_active_season`, 02:00 UTC) creates, syncs and activates the new season without
a restart or a manual command. Run the two commands above only to bootstrap the first
season, or to bring a rollover forward rather than waiting for the nightly job.

Restarting the container does *not* roll the season over: `scripts/startup.py` skips
season setup whenever the active season already has teams and games.

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

`NFL_API_USER_AGENT` overrides the User-Agent sent to the NFL data feed. The default
identifies the app and links back to this repo. Set it only if the feed starts answering
`403 Forbidden` to the default - the edge filters on this header, and a plain
`curl/8.14.1` or `python-requests/2.32.3` also gets through. A rejected User-Agent fails
every sync, which stalls live scores *and* the season rollover.

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

Manual runs (Actions -> Run workflow) take four inputs:

- `version_bump` — `patch` / `minor` / `major` bumps the latest `v*` tag (for example
  `v1.2.41` -> `v1.2.42`); `none` builds without creating a tag
- `version` — an explicit tag such as `v1.2.3`, overriding `version_bump`
- `push_latest` — also publish `:latest`
- `no_cache` — build with `--no-cache`

A bumped run stamps `app.__version__` (what `/health` reports) with the tag being
published, commits that stamp to the branch, and pushes the tag.

## CI / Build workflows

This repository uses the same workflow pattern as other -chen projects:

- **CI**: [.github/workflows/ci.yml](.github/workflows/ci.yml)
    - Lint (`ruff check .`)
    - Unit tests (`pytest`)
    - Runtime smoke test (Gunicorn boot + HTTP/WebSocket check)
    - PR Docker build validation (`linux/amd64`, no push)
- **Release build**: [.github/workflows/build-multiarch.yml](.github/workflows/build-multiarch.yml)
    - Triggered by `v*` tags or manually
    - Publishes multi-arch images (`linux/amd64` + `linux/arm64`) to GHCR

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
python manage.py sync all 2026                   # Create the season, sync teams + schedule
python manage.py season activate 2026            # Make it the season the app serves
python manage.py season list-seasons             # List seasons and which one is active
python manage.py season finalize 2025            # Award winners once the Super Bowl is final
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

It also never reshapes an index that already exists, even when the model's definition of
it has changed.

So when you add a column to an existing model, or change an existing index, register it in
[`app/utils/schema_guard.py`](app/utils/schema_guard.py). The guard runs on every startup
and applies each change with idempotent DDL, on both PostgreSQL and SQLite:

- `COLUMNS` — added with `ALTER TABLE`. Skipping this is the usual cause of an
  `UndefinedColumn` error after deploying a model change to an existing database.
- `DROP_UNIQUE_INDEXES` — dropped and recreated without `UNIQUE`, for an index that
  shipped unique but should not be.
- `UNIQUE_INDEXES` — created where an existing database lacks them.

The index entries exist because `teams.espn_id` shipped globally unique while teams are
per-season rows, so the same franchise repeats every year. That made the second season's
teams impossible to insert and blocked every season rollover until the guard relaxed it.

## Troubleshooting

### The app still shows last season

Everything the app serves is keyed off the single season row with `is_active = true`, so
a group showing last season's final standings means the rollover did not happen. Check
which season is active and whether the syncs are succeeding:

```bash
docker compose exec web python manage.py season list-seasons
docker compose logs --since 48h web | grep -iE "season|maintenance"
```

`_ensure_active_season` needs a successful data-feed sync before it can create the new
season, so anything that breaks syncing also silently blocks the rollover — it logs
`Could not sync season <year> yet: ...` and gives up until the next night. The two causes
seen so far:

- **`403 Forbidden` from the data feed** — the User-Agent is being filtered. Set
  `NFL_API_USER_AGENT` (see [Configuration](#configuration)) and restart.
- **`duplicate key value violates unique constraint "ix_teams_espn_id"`** — an old
  database still carries the global unique index on `teams.espn_id`. Restart the app; the
  schema guard relaxes it at startup.

Restarting alone never forces a rollover, so once the underlying cause is fixed either
wait for the 02:00 UTC job or run the [First season setup](#first-season-setup) commands
for the new year.

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

## Support

If you run this project and want to support ongoing maintenance, configure the optional footer links in [.env.example](.env.example):

- `CONTACT_KOFI`
- `CONTACT_BUYMEACOFFEE`

They render as small footer support chips only when set.

See [CHANGELOG.md](CHANGELOG.md) for version history.

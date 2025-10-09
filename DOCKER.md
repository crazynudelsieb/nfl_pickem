# Docker Setup Guide

Quick reference for running the NFL Pick'em application with Docker.

## Quick Start

```powershell
# 1. Copy environment file
Copy-Item .env.docker.example .env

# 2. Generate secrets
python generate_secrets.py

# 3. Start services
docker compose up -d

# 4. View logs
docker compose logs -f web
```

Access at: http://localhost:5000

## Services

- **web**: Flask application (port 5000)
- **db**: PostgreSQL database (port 5432)
- **redis**: Redis cache (port 6379)

## Common Commands

```powershell
# Rebuild and restart
docker compose up --build -d

# Stop services
docker compose down

# Stop and remove volumes (CAUTION: deletes data)
docker compose down -v

# View running containers
docker compose ps

# Execute commands in container
docker compose exec web python manage.py <command>

# Database backup
docker compose exec db pg_dump -U nfl_user nfl_pickem_db > backup.sql

# Database restore
cat backup.sql | docker compose exec -T db psql -U nfl_user -d nfl_pickem_db
```

## Environment Variables

Key variables in `.env`:

```bash
# Security (required)
SECRET_KEY=<generate-with-script>
WTF_CSRF_SECRET_KEY=<generate-with-script>

# Database
DATABASE_URL=postgresql://nfl_user:nfl_password@db:5432/nfl_pickem_db

# Redis
REDIS_URL=redis://redis:6379/0

# App Config
FLASK_ENV=production
```

## Troubleshooting

**Container won't start:**
```powershell
# Check logs
docker compose logs web

# Verify .env file exists
Test-Path .env
```

**Database connection issues:**
```powershell
# Ensure db is running
docker compose ps db

# Check db logs
docker compose logs db
```

**Port already in use:**
```powershell
# Change ports in docker-compose.yml
ports:
  - "5001:5000"  # Use 5001 instead
```

## Multi-Stage Build

The Dockerfile uses multi-stage builds for optimization:
- **builder**: Compiles dependencies
- **runtime**: Minimal production image (210MB vs 950MB)

## Production Tips

1. Use volumes for persistent data (already configured)
2. Set `FLASK_ENV=production` in .env
3. Configure proper SECRET_KEY values
4. Regular database backups
5. Monitor logs with `docker compose logs -f`
6. Update images regularly: `docker compose pull`

## Development Mode

For local development without Docker, see README.md.

---

For more details, see `docker-compose.yml` and `Dockerfile`.

# NFL Pick'em

A modern Progressive Web App for managing NFL Pick'em leagues with real-time updates and mobile-first design.

## Features

- **Weekly Picks**: Select one team per week to win
- **Smart Rules**: Teams can only be selected once during regular season, penalties for consecutive losses
- **Multiple Groups**: Create and join unlimited pick'em leagues
- **Real-time Updates**: Live scores via WebSockets
- **PWA Support**: Install as native app on any device
- **Mobile Optimized**: Responsive design with touch-friendly interface
- **Scoring**: 
- **Win**: 1 point
- **Tie**: 0.5 points (half point)
- **Loss**: 0 points
- **Tiebreaker**: Margin of victory (winning pick) or negative margin (losing pick) stored in `Pick.tiebreaker_points`
- **Leaderboards**: Sort by `total_score` (includes 0.5 for ties), then by `tiebreaker_points`
- **Admin Tools**: Manage picks, view audit logs, control scheduler

## Quick Start

### Using Pre-built Images (Recommended)

```bash
# Clone repository
git clone https://github.com/crazynudelsieb/nfl_pickem.git
cd nfl_pickem

# Generate secrets
python generate_secrets.py

# Start with pre-built images
docker compose up -d

# Access at http://localhost:5000
```

### Building Locally

```bash
# Use local development compose
docker compose -f docker-compose.local.yml up --build -d
```

For detailed build instructions including multi-architecture builds, see [BUILD.md](BUILD.md).

### Prerequisites
- Docker & Docker Compose
- Git

### Create Admin User

```bash
docker compose exec web python -c "from app import db; from app.models import User; u = User.query.filter_by(username='YOUR_USERNAME').first(); u.is_admin = True; db.session.commit()"
```

## Technology Stack

**Backend**: Python 3.12, Flask, SQLAlchemy, PostgreSQL, Redis  
**Frontend**: Jinja2, Vanilla JS, Custom CSS, Socket.IO  
**Infrastructure**: Docker, Gunicorn, Nginx (recommended)  
**Features**: PWA, WebSockets, Background Jobs, REST API

## Configuration

Edit `.env` file:

```env
FLASK_ENV=production
SECRET_KEY=<generate with generate_secrets.py>
WTF_CSRF_SECRET_KEY=<generate with generate_secrets.py>
DATABASE_URL=postgresql://user:pass@db:5432/nfl_pickem
REDIS_URL=redis://redis:6379/0
```

## Security Notice

🔒 **Important Security Guidelines**

- **Change Default Passwords**: Always change the default admin password after first login
- **Use Strong Secrets**: Generate secure keys with `python generate_secrets.py` - never use defaults in production
- **Environment Variables**: Never commit `.env` files with real credentials to version control
- **Admin Password**: Set `DEFAULT_ADMIN_PASSWORD` environment variable for secure admin account creation
- **HTTPS Required**: Use HTTPS/TLS in production (recommended: Let's Encrypt with reverse proxy)
- **Regular Updates**: Keep dependencies and Docker images updated for security patches

For detailed security guidance, see [SECURITY.md](SECURITY.md).

## Project Structure

```
app/
├── models/          # Database models (User, Pick, Game, Season, Team, Group)
├── routes/          # API & page routes (auth, main, groups, api)
├── services/        # Background services (scheduler_service)
├── static/          # CSS, JS, PWA assets (manifest.json, sw.js)
├── templates/       # Jinja2 templates (base, main, auth, groups, errors)
└── utils/           # Helper functions (scoring, data_sync, cache_utils)
```

### Key Files
- **`app/models/user.py`**: User stats & leaderboard methods (`get_season_stats()`, `get_season_leaderboard()`)
- **`app/models/pick.py`**: Pick validation & scoring (`is_valid_pick()`, `update_result()`)
- **`app/models/game.py`**: Game state & tie detection (`is_tie`, `is_final`, `winning_team`)
- **`app/utils/scoring.py`**: Individual pick scoring (`ScoringEngine.calculate_pick_score()`)
- **`app/services/scheduler_service.py`**: Background data sync (ESPN API integration)
- **`config.py`**: Environment-specific configuration classes
- **`.github/copilot-instructions.md`**: AI agent instructions for development

## Usage

1. **Sign Up**: Create account
2. **Join/Create Group**: Use invite code or create new league
3. **Make Picks**: Select one game per week before kickoff
4. **Track Progress**: View leaderboards and personal stats
5. **Follow Rules**: No team reuse in regular season, avoid consecutive losses

## API Endpoints

```
GET  /api/seasons/current         # Current season data
GET  /api/groups/<id>/leaderboard # Group standings
GET  /api/picks                   # User picks with filters
POST /picks/make/<game_id>        # Submit pick
```

See application for complete API documentation.

## Production Deployment

1. **Server Setup**: Ubuntu 20.04+, 2GB RAM, Docker installed
2. **Clone & Configure**: Set production values in `.env`
3. **Deploy**: `docker compose up -d`
4. **Nginx Proxy**: Configure reverse proxy with SSL
5. **Monitoring**: Check logs with `docker compose logs -f`

### Nginx Example

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
# Local setup
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run dev server
export FLASK_ENV=development
python run.py

# Database migrations
flask db migrate -m "Description"
flask db upgrade
```

### Recent Changes (v1.0.13 - v1.0.16)

**Tie Game Support & Scoring Fixes**:
- ✅ Added tri-state `Pick.is_correct` (True/False/None for ties)
- ✅ Tie games award 0.5 points correctly
- ✅ Fixed leaderboards to display `total_score` (wins + 0.5×ties) instead of just win count
- ✅ Fixed `User.get_season_leaderboard()` to sort by `total_score` not wins
- ✅ UI shows yellow "TIE" indicator for tied games
- ✅ Modal displays correct tie status with points

**Code Cleanup (cleanup-unused-scoring-code branch)**:
- ✅ Removed ~240 lines of unused `ScoringEngine` methods
- ✅ Single source of truth: `User.get_season_stats()` and `User.get_season_leaderboard()`
- ✅ Simplified architecture following KISS principle
- ✅ Easy revert: `git checkout main` or `git revert <commit>`

See [CHANGELOG.md](CHANGELOG.md) for complete version history.

## Mobile Optimization

- Touch-friendly buttons (min 44x44px)
- Responsive breakpoints for all screen sizes
- PWA installable on home screen
- Offline mode with service worker caching
- Fast load times with optimized assets

## License

MIT License with Commercial Use Restriction - see [LICENSE](LICENSE) file.  
Non-commercial use freely permitted. Contact for commercial licensing.

## Contributing

1. Fork repository
2. Create feature branch
3. Commit changes
4. Push to branch
5. Open Pull Request

## Support

- **Issues**: [GitHub Issues](https://github.com/crazynudelsieb/nfl_pickem/issues)
- **Source**: [GitHub Repository](https://github.com/crazynudelsieb/nfl_pickem)
- **License**: Contact for commercial use inquiries

---

**Built with ❤️ for NFL fans** | [Source Code](https://github.com/crazynudelsieb/nfl_pickem)

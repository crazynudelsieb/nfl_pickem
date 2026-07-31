# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| main | :white_check_mark: |
| older tags | :x: |

## Reporting a Vulnerability

Please do not open public issues for security vulnerabilities.

1. Open a private advisory: https://github.com/crazynudelsieb/nfl_pickem/security/advisories/new
2. Or contact: appchen@outlook.at
3. Include:
   - Affected component and impact
   - Reproduction steps or proof-of-concept
   - Suggested mitigation (optional)

### Response Targets

- Acknowledge report within 48 hours
- Initial triage within 7 days
- Critical fixes targeted within 30 days

## Security Baseline for Operators

- Set explicit, high-entropy values for `SECRET_KEY` and `WTF_CSRF_SECRET_KEY`
- Keep `.env` private and out of version control
- Set a strong `DEFAULT_ADMIN_PASSWORD` for first boot or rotate immediately
- Run behind HTTPS/TLS in production
- Keep host OS, container base image, and Python dependencies patched
- Restrict database/network access to required services only

## Security Features in This Repository

- CSRF protection via Flask-WTF
- Authentication/session handling via Flask-Login
- Input validation via WTForms
- SQL injection mitigation via SQLAlchemy ORM
- Rate limiting via Flask-Limiter
- Non-root container runtime in Docker setup

## Responsible Disclosure

If you report a valid issue, you can be credited in the advisory unless you prefer to stay anonymous.

## Scope Notes

This project is source-available under PolyForm Noncommercial and is intended for self-hosted deployments. Final runtime security also depends on your infrastructure, reverse proxy, TLS setup, and secrets management.

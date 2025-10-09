# Security Policy

## Supported Versions

We actively maintain and provide security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you believe you have found a security vulnerability in NFL Pick'em, please report it responsibly.

### How to Report

1. **DO NOT** create a public GitHub issue for security vulnerabilities
2. Email the maintainers at [repository owner's email] with details
3. Include the following information:
   - Description of the vulnerability
   - Steps to reproduce the issue
   - Potential impact assessment
   - Suggested fix (if available)

### What to Expect

- **Acknowledgment**: We'll acknowledge receipt within 48 hours
- **Initial Assessment**: We'll provide an initial assessment within 7 days
- **Regular Updates**: We'll keep you informed of our progress
- **Resolution**: We aim to resolve critical vulnerabilities within 30 days

### Responsible Disclosure

We follow responsible disclosure practices:
- We'll work with you to understand and resolve the issue
- We'll credit you in our security advisory (unless you prefer anonymity)
- We ask that you don't publicly disclose the vulnerability until we've had a chance to fix it

## Security Best Practices

### For Administrators

#### Environment Variables
- **Always** set strong, unique values for `SECRET_KEY` and `WTF_CSRF_SECRET_KEY`
- Use the provided `generate_secrets.py` script to generate secure keys
- Never commit `.env` files containing real credentials

#### Database Security
- Use strong, unique passwords for database users
- Limit database access to only necessary services
- Regularly update database software and apply security patches

#### Admin Account Security
- **Change the default admin password immediately** after first login
- Use strong, unique passwords for all admin accounts
- Enable two-factor authentication if available
- Regularly audit admin user accounts

#### Production Deployment
- Use HTTPS/TLS for all communications (recommended: Let's Encrypt)
- Set up proper firewall rules
- Keep Docker images and host system updated
- Use non-root containers when possible
- Implement proper backup strategies

#### Environment-Specific Settings
```env
# Production Security Settings
FLASK_ENV=production
FLASK_DEBUG=False

# Use strong, unique keys (never use defaults in production)
SECRET_KEY=<generate with generate_secrets.py>
WTF_CSRF_SECRET_KEY=<generate with generate_secrets.py>

# Set a strong admin password
DEFAULT_ADMIN_PASSWORD=<strong-unique-password>

# Use secure database credentials
DATABASE_URL=postgresql://secure_user:strong_password@db:5432/nfl_pickem_db
```

### For Developers

#### Code Security
- Follow secure coding practices
- Validate all user inputs
- Use parameterized queries (SQLAlchemy ORM handles this)
- Implement proper authentication and authorization
- Keep dependencies updated

#### Development Environment
- Never use production credentials in development
- Use the provided `.env.example` as a template
- Keep `.env` files out of version control
- Use different secrets for each environment

## Security Features

### Built-in Security Measures

- **CSRF Protection**: All forms protected with Flask-WTF CSRF tokens
- **SQL Injection Prevention**: SQLAlchemy ORM with parameterized queries
- **Password Security**: bcrypt hashing for all passwords
- **Session Security**: Secure session handling with Flask-Login
- **Input Validation**: WTForms validation for all user inputs
- **Rate Limiting**: Flask-Limiter protection against abuse

### Docker Security

- Non-privileged containers with `security_opt: no-new-privileges:true`
- Resource limits to prevent resource exhaustion
- Health checks for service monitoring
- Isolated networks for service communication

## Security Updates

We regularly monitor for security vulnerabilities in our dependencies and will:
- Update dependencies when security patches are available
- Communicate security updates through GitHub releases
- Provide migration guidance for breaking security changes

## Compliance

This application is designed with security best practices in mind:
- OWASP Top 10 considerations
- Modern web security standards
- Privacy-by-design principles

## Contact

For security-related questions or concerns:
- Security vulnerabilities: [Follow reporting process above]
- General security questions: [GitHub Discussions or Issues]
- Commercial security inquiries: [Contact repository owner]

---

**Last Updated**: October 2025  
**Next Review**: January 2026
#!/usr/bin/env python3
"""
Generate secure secrets for NFL Pick'em application
Run this script to generate the required SECRET_KEY and WTF_CSRF_SECRET_KEY
"""

import secrets


def generate_secrets():
    """Generate secure random keys for the application"""
    print("🔐 Generating secure secrets for NFL Pick'em...")
    print("=" * 50)

    secret_key = secrets.token_urlsafe(32)
    csrf_key = secrets.token_urlsafe(32)

    print(f"SECRET_KEY={secret_key}")
    print(f"WTF_CSRF_SECRET_KEY={csrf_key}")

    print("=" * 50)
    print("📝 Copy these values to your .env file")
    print("⚠️  Keep these secrets secure and never commit them to version control!")


if __name__ == "__main__":
    generate_secrets()

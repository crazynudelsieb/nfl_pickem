#!/bin/bash
set -e

echo "🏈 Starting NFL Pick'em Application..."

# Run auto-initialization
echo "🔄 Running auto-initialization..."
python3 /app/scripts/startup.py

# Start the main application
echo "🚀 Starting Flask application..."
exec "$@"
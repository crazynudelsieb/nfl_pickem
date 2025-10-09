-- Initialize database with extensions and basic setup
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create indexes for performance
-- These will be created by SQLAlchemy, but we can add custom ones here if needed

-- Set default timezone
SET timezone = 'UTC';
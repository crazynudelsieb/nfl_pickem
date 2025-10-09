# Build Documentation

This document provides comprehensive instructions for building and deploying the NFL Pick'em application, including multi-architecture Docker builds and CI/CD pipeline setup.

## Quick Start

### Using Pre-built Images (Recommended)

```powershell
# Pull the latest image
docker pull ghcr.io/crazynudelsieb/nfl_pickem:latest

# Start the application
docker compose up -d
```

### Building Locally

```powershell
# Build for local architecture
docker build -t nfl-pickem .

# Run locally built image
docker compose -f docker-compose.local.yml up -d
```

## Multi-Architecture Builds

The project supports building for multiple architectures using Docker Buildx.

### Prerequisites

1. **Docker Buildx**: Ensure Docker Desktop is installed with buildx support
2. **Registry Authentication**: GitHub Container Registry access for pushing images

```powershell
# Verify buildx is available
docker buildx version

# Create and use a multi-platform builder
docker buildx create --name multiarch --use
docker buildx inspect --bootstrap
```

### PowerShell Build Script

Use the provided `build-multiarch.ps1` script for local multi-architecture builds:

```powershell
# Build and push latest
.\build-multiarch.ps1

# Build specific version
.\build-multiarch.ps1 -Version "1.2.3"

# Build without pushing (test only)
.\build-multiarch.ps1 -NoPush

# Build with custom registry
.\build-multiarch.ps1 -Registry "your-registry.com/your-username"

# Show help
.\build-multiarch.ps1 -Help
```

#### Script Features

- **Multi-platform support**: linux/amd64, linux/arm64, linux/arm/v7
- **Semantic versioning**: Automatic tagging with major.minor and major versions
- **Registry authentication**: Interactive GitHub login if not authenticated
- **Build caching**: Optimized layer caching for faster builds
- **Error handling**: Comprehensive validation and rollback

#### Supported Platforms

| Platform | Architecture | Use Case |
|----------|-------------|----------|
| linux/amd64 | x86_64 | Standard servers, dev machines |
| linux/arm64 | ARM64/v8 | Apple Silicon, AWS Graviton |
| linux/arm/v7 | ARMv7 | Raspberry Pi, IoT devices |

### Manual Build Commands

For advanced users who prefer manual control:

```powershell
# Authenticate with GitHub Container Registry
echo $env:GITHUB_TOKEN | docker login ghcr.io -u your-username --password-stdin

# Build and push multi-arch image
docker buildx build `
  --platform linux/amd64,linux/arm64,linux/arm/v7 `
  --tag ghcr.io/your-username/nfl_pickem:latest `
  --tag ghcr.io/your-username/nfl_pickem:1.0.0 `
  --push .
```

## CI/CD Pipeline

### GitHub Actions Workflow

The project includes an automated CI/CD pipeline (`.github/workflows/docker-multiarch.yml`) that:

1. **Triggers**: On version tags (v*) and manual dispatch
2. **Builds**: Multi-architecture images automatically
3. **Pushes**: To GitHub Container Registry
4. **Caches**: Docker layers for optimization

#### Triggering Builds

```powershell
# Create and push a version tag
git tag v1.2.3
git push origin v1.2.3

# Manual trigger via GitHub Actions web interface
# Go to Actions → Docker Multi-Architecture Build → Run workflow
```

#### Workflow Features

- **Automatic versioning**: Extracts version from git tags
- **Multi-platform builds**: Same platforms as local script
- **Registry management**: Automatic login and layer caching
- **Build optimization**: Cached dependencies and layers

### Registry Authentication

#### Local Development

```powershell
# Create a GitHub Personal Access Token with packages:write scope
# https://github.com/settings/tokens/new

# Login to registry
$env:GITHUB_TOKEN = "your_token_here"
echo $env:GITHUB_TOKEN | docker login ghcr.io -u your-username --password-stdin
```

#### CI/CD Environment

The GitHub Actions workflow uses `GITHUB_TOKEN` automatically provided by GitHub Actions with appropriate permissions.

## Deployment Options

### Production Deployment

```powershell
# Create production environment file
cp .env.example .env
# Edit .env with production values

# Deploy with pre-built images
docker compose up -d

# Monitor logs
docker compose logs -f web
```

### Development Deployment

```powershell
# Use local build for development
docker compose -f docker-compose.local.yml up -d --build
```

### Environment Configuration

Key environment variables for deployment:

```bash
# Required
SECRET_KEY=your-secret-key
WTF_CSRF_SECRET_KEY=your-csrf-key
DB_PASSWORD=secure-database-password

# Optional
DEFAULT_ADMIN_PASSWORD=secure-admin-password
TIMEZONE=Europe/Vienna
LOG_LEVEL=INFO
```

## Build Optimization

### Layer Caching

The Dockerfile is optimized for layer caching:

1. **Dependencies first**: Requirements installation before code copy
2. **Multi-stage builds**: Separate build and runtime stages
3. **Minimal base images**: Alpine Linux for smaller images

### Build Performance Tips

```powershell
# Use buildx cache mount for faster dependency installation
docker buildx build --cache-from type=gha --cache-to type=gha,mode=max .

# Local cache for repeated builds
docker buildx build --cache-from type=local,src=/tmp/.buildx-cache .
```

## Troubleshooting

### Common Issues

#### Buildx Not Available
```powershell
# Install buildx plugin
docker buildx install
docker buildx create --use
```

#### Registry Authentication Failed
```powershell
# Check token permissions (needs packages:write)
# Verify username matches GitHub username exactly
docker logout ghcr.io
echo $env:GITHUB_TOKEN | docker login ghcr.io -u your-username --password-stdin
```

#### Build Platform Errors
```powershell
# Reset builder instance
docker buildx rm multiarch
docker buildx create --name multiarch --use
docker buildx inspect --bootstrap
```

#### Memory Issues During Build
```powershell
# Increase Docker Desktop memory allocation
# Or build platforms separately:
docker buildx build --platform linux/amd64 --tag image:amd64 .
docker buildx build --platform linux/arm64 --tag image:arm64 .
```

### Debug Commands

```powershell
# Inspect built image
docker buildx imagetools inspect ghcr.io/your-username/nfl_pickem:latest

# Test image on specific platform
docker run --platform linux/arm64 ghcr.io/your-username/nfl_pickem:latest

# Check builder configuration
docker buildx ls
docker buildx inspect
```

## Security Considerations

### Registry Security

- Use personal access tokens instead of passwords
- Limit token scope to `packages:write` only
- Rotate tokens regularly
- Use organization secrets for team projects

### Image Security

- Images run as non-root user
- Security options enabled in docker-compose
- Regular base image updates via automated builds
- Vulnerability scanning in CI/CD pipeline

### Build Security

- No secrets embedded in images
- Multi-stage builds minimize attack surface
- Reproducible builds with version pinning
- Signed commits for tag releases

## Performance Monitoring

### Build Metrics

Monitor build performance through:

- GitHub Actions build times
- Docker layer cache hit rates
- Registry push/pull speeds
- Multi-platform build parallelization

### Runtime Metrics

- Container resource usage (CPU, memory)
- Application startup times
- Health check response times
- Log aggregation and monitoring

## Support

For build-related issues:

1. Check this documentation
2. Review GitHub Actions logs
3. Validate Docker Buildx configuration
4. Consult Docker's multi-platform documentation
5. Open an issue with build environment details

## Version History

- **v1.0.0**: Initial public release with multi-arch builds
- **Latest**: Current development version

For complete changelog, see [CHANGELOG.md](CHANGELOG.md).
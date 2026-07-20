# Multi-platform Docker build script for nfl_pickem
# Builds for both AMD64 (development/testing) and ARM64 (OCI production)

Set-Location "C:\git\nfl_pickem"

# Use the multiarch-builder (configured with QEMU for ARM64 support)
Write-Host "Using multiarch-builder for multi-arch build..." -ForegroundColor Cyan
docker buildx use multiarch-builder

function Invoke-MultiArchBuild {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Image,
        [Parameter(Mandatory = $true)]
        [string]$Dockerfile
    )

    Write-Host "`nBuilding image: $Image" -ForegroundColor Yellow
    docker buildx build `
        --platform linux/amd64,linux/arm64 `
        --no-cache `
        -t $Image `
        -f $Dockerfile `
        --push `
        .

    if ($LASTEXITCODE -ne 0) {
        Write-Host "`nBuild failed for $Image with exit code $LASTEXITCODE" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Write-Host "`nBuilding multi-platform image for linux/amd64 and linux/arm64..." -ForegroundColor Yellow
Write-Host "This may take several minutes on first build..." -ForegroundColor Gray

Invoke-MultiArchBuild -Image "ghcr.io/crazynudelsieb/nfl_pickem:latest" -Dockerfile "Dockerfile"

Write-Host "`nMulti-arch build completed successfully!" -ForegroundColor Green
Write-Host "Image pushed:" -ForegroundColor Cyan
Write-Host " - ghcr.io/crazynudelsieb/nfl_pickem:latest" -ForegroundColor Cyan
Write-Host "Platforms: linux/amd64, linux/arm64" -ForegroundColor Gray

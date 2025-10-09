"""
Generate PWA icons from the NFL logo.
This script creates multiple icon sizes required for PWA from the base nfl-logo.png
"""

import os
from io import BytesIO

import requests
from PIL import Image

# Icon sizes needed for PWA
ICON_SIZES = [72, 96, 128, 144, 152, 192, 384, 512]

# NFL logo URL (used in the app)
NFL_LOGO_URL = "https://a.espncdn.com/i/teamlogos/leagues/500/nfl.png"


def generate_icons():
    """Generate all icon sizes from the base NFL logo"""
    # Get paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    images_dir = os.path.join(project_root, "app", "static", "images")

    source_image = os.path.join(images_dir, "nfl-logo.png")

    print(f"Downloading NFL logo from {NFL_LOGO_URL}")

    try:
        # Download the NFL logo
        response = requests.get(NFL_LOGO_URL, timeout=10)
        response.raise_for_status()

        # Open the image from bytes
        img = Image.open(BytesIO(response.content))

        # Save the original as well
        img.save(source_image, "PNG", optimize=True)
        print(f"✓ Saved original NFL logo to: {source_image}")

        # Convert to RGBA if not already
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        print(f"Original image size: {img.size}")

        # Generate each icon size
        for size in ICON_SIZES:
            output_path = os.path.join(images_dir, f"icon-{size}x{size}.png")

            # Resize with high-quality resampling
            resized = img.resize((size, size), Image.Resampling.LANCZOS)

            # Save the resized icon
            resized.save(output_path, "PNG", optimize=True)
            print(f"✓ Generated: icon-{size}x{size}.png")

        # Also create a favicon.ico with multiple sizes
        favicon_path = os.path.join(project_root, "app", "static", "favicon.ico")
        favicon_sizes = [(16, 16), (32, 32), (48, 48)]
        favicon_images = [
            img.resize(size, Image.Resampling.LANCZOS) for size in favicon_sizes
        ]

        # Save as ICO with multiple sizes
        favicon_images[0].save(favicon_path, format="ICO", sizes=favicon_sizes)
        print(f"✓ Generated: favicon.ico")

        # Create apple-touch-icon (180x180 for iOS)
        apple_icon_path = os.path.join(images_dir, "apple-touch-icon.png")
        apple_icon = img.resize((180, 180), Image.Resampling.LANCZOS)
        apple_icon.save(apple_icon_path, "PNG", optimize=True)
        print(f"✓ Generated: apple-touch-icon.png")

        print("\n✅ All PWA icons generated successfully!")
        print("\nGenerated files:")
        print("  - favicon.ico (in app/static/)")
        print("  - apple-touch-icon.png (in app/static/images/)")
        for size in ICON_SIZES:
            print(f"  - icon-{size}x{size}.png (in app/static/images/)")

    except Exception as e:
        print(f"Error generating icons: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    print("NFL Pick'em PWA Icon Generator")
    print("=" * 50)
    generate_icons()

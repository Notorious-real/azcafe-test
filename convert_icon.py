# ============================================================
#  AZ Cafe - Convert logo.png to logo.ico
#  Run this ONCE before building the .exe files
#  Usage: python convert_icon.py
# ============================================================

import os
import sys

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow not installed.")
    print("Run: pip install Pillow")
    sys.exit(1)

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
PNG_PATH   = os.path.join(ASSETS_DIR, "logo.png")
ICO_PATH   = os.path.join(ASSETS_DIR, "logo.ico")

def convert():
    if not os.path.exists(PNG_PATH):
        print(f"ERROR: logo.png not found at {PNG_PATH}")
        sys.exit(1)

    img = Image.open(PNG_PATH).convert("RGBA")

    # Generate multiple sizes for a proper .ico file
    sizes = [(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)]
    icons = []
    for size in sizes:
        resized = img.resize(size, Image.LANCZOS)
        icons.append(resized)

    # Save as ICO with all sizes embedded
    icons[0].save(
        ICO_PATH,
        format="ICO",
        sizes=[(i.width, i.height) for i in icons],
        append_images=icons[1:]
    )
    print(f"SUCCESS: logo.ico created at {ICO_PATH}")
    print(f"         Sizes: {[f'{s[0]}x{s[1]}' for s in sizes]}")

if __name__ == "__main__":
    convert()

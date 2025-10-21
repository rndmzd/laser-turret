#!/usr/bin/env python3
import sys, json
from pathlib import Path
from io import BytesIO
from PIL import Image

# Optional SVG -> PNG
try:
    import cairosvg
    HAS_CAIROSVG = True
except Exception:
    HAS_CAIROSVG = False

USAGE = """Usage:
  py generate_favicons.py path/to/logo.(svg|png) [out_dir] [app_name] [theme_color]
Example:
  py generate_favicons.py logo.svg public "My App" "#0f172a"
"""

def load_image(src: Path) -> Image.Image:
    if src.suffix.lower() == ".svg":
        if not HAS_CAIROSVG:
            sys.exit("SVG input requires cairosvg. Install: py -m pip install cairosvg")
        png_bytes = cairosvg.svg2png(url=str(src), output_width=2048, output_height=2048)
        return Image.open(BytesIO(png_bytes)).convert("RGBA")
    # PNG or other raster
    return Image.open(src).convert("RGBA")

def square_pad(im: Image.Image, size: int) -> Image.Image:
    # letterbox to square with transparent background, then fit
    w, h = im.size
    s = max(w, h)
    canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    canvas.paste(im, ((s - w)//2, (s - h)//2))
    return canvas.resize((size, size), Image.LANCZOS)

def save_png(im: Image.Image, path: Path, size: int):
    out = im.resize((size, size), Image.LANCZOS)
    out.save(path, format="PNG", optimize=True)

def main():
    if len(sys.argv) < 2:
        print(USAGE); sys.exit(1)
    src = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) >= 3 else Path("public")
    app_name = sys.argv[3] if len(sys.argv) >= 4 else "My App"
    theme = sys.argv[4] if len(sys.argv) >= 5 else "#111111"

    if not src.exists():
        sys.exit(f"Source not found: {src}")

    out_dir.mkdir(parents=True, exist_ok=True)

    # Base 1024x1024
    base = square_pad(load_image(src), 1024)
    base_1024 = out_dir / "appicon-1024.png"
    base.save(base_1024, format="PNG", optimize=True)

    # Targets
    sizes = [16, 32, 48, 180, 192, 512]
    png_map = {}
    for s in sizes:
        p = out_dir / f"icon-{s}x{s}.png"
        save_png(base, p, s)
        png_map[s] = p

    # Friendly names
    (out_dir / "favicon-32x32.png").write_bytes(png_map[32].read_bytes())
    (out_dir / "apple-touch-icon.png").write_bytes(png_map[180].read_bytes())
    (out_dir / "android-chrome-192x192.png").write_bytes(png_map[192].read_bytes())
    (out_dir / "android-chrome-512x512.png").write_bytes(png_map[512].read_bytes())

    # Maskable (same content; Android uses "purpose":"maskable")
    for s in (192, 512):
        mask_p = out_dir / f"android-chrome-{s}x{s}-maskable.png"
        save_png(base, mask_p, s)

    # favicon.ico with 16,32,48
    ico_path = out_dir / "favicon.ico"
    ico_images = [Image.open(png_map[n]).convert("RGBA") for n in (16, 32, 48)]
    ico_images[0].save(
        ico_path,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)]
    )

    # site.webmanifest
    manifest = {
        "name": app_name,
        "short_name": app_name,
        "icons": [
            {"src": "/android-chrome-192x192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/android-chrome-512x512.png", "sizes": "512x512", "type": "image/png"},
            {"src": "/android-chrome-192x192-maskable.png", "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
            {"src": "/android-chrome-512x512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}
        ],
        "start_url": "/",
        "display": "standalone",
        "background_color": theme,
        "theme_color": theme
    }
    (out_dir / "site.webmanifest").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Head snippet
    head_snippet = """\
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<meta name="theme-color" content="{theme}">
""".format(theme=theme)
    (out_dir / "HEAD_SNIPPET.html").write_text(head_snippet, encoding="utf-8")

    print(f"Done -> {out_dir}")
    print("Add these to <head> (also saved as HEAD_SNIPPET.html):\n")
    print(head_snippet)

if __name__ == "__main__":
    main()

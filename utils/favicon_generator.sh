#!/usr/bin/env bash
set -euo pipefail

# Usage: ./generate_favicons.sh path/to/logo.(svg|png) [out_dir] [app_name] [theme_color]
# Example: ./generate_favicons.sh logo.svg public "My App" "#0f172a"

SRC="${1:-}"; OUT="${2:-public}"; APP_NAME="${3:-My App}"; THEME="${4:-#111111}"

if [[ -z "$SRC" || ! -f "$SRC" ]]; then
  echo "Give me a source image file (SVG or large PNG)."; exit 1
fi

command -v convert >/dev/null 2>&1 || { echo "Install ImageMagick (convert)."; exit 1; }

mkdir -p "$OUT"

# Target sizes
png_sizes=(16 32 180 192 512)

# Produce base 1024 px raster first for quality (from SVG or big PNG)
convert "$SRC" -resize 1024x1024 -background none -gravity center -extent 1024x1024 "$OUT/appicon-1024.png"

# Generate required PNGs
for s in "${png_sizes[@]}"; do
  convert "$OUT/appicon-1024.png" -resize ${s}x${s} "$OUT/icon-${s}x${s}.png"
done

# Friendly filenames per platform conventions
cp "$OUT/icon-32x32.png"  "$OUT/favicon-32x32.png"
cp "$OUT/icon-180x180.png" "$OUT/apple-touch-icon.png"
cp "$OUT/icon-192x192.png" "$OUT/android-chrome-192x192.png"
cp "$OUT/icon-512x512.png" "$OUT/android-chrome-512x512.png"

# favicon.ico with 16 and 32
convert "$OUT/icon-16x16.png" "$OUT/icon-32x32.png" -colors 256 "$OUT/favicon.ico"

# Optional maskable icons (improves Android adaptive icon rendering)
convert "$OUT/appicon-1024.png" -resize 192x192 "$OUT/android-chrome-192x192-maskable.png"
convert "$OUT/appicon-1024.png" -resize 512x512 "$OUT/android-chrome-512x512-maskable.png"

# site.webmanifest
cat > "$OUT/site.webmanifest" <<JSON
{
  "name": "${APP_NAME}",
  "short_name": "${APP_NAME}",
  "icons": [
    { "src": "/android-chrome-192x192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/android-chrome-512x512.png", "sizes": "512x512", "type": "image/png" },
    { "src": "/android-chrome-192x192-maskable.png", "sizes": "192x192", "type": "image/png", "purpose": "maskable" },
    { "src": "/android-chrome-512x512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ],
  "start_url": "/",
  "display": "standalone",
  "background_color": "${THEME}",
  "theme_color": "${THEME}"
}
JSON

# Minimal robots and browserconfig are optional; skip for brevity.

cat <<'HTML'

Add this to <head>:

<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<meta name="theme-color" content="#111111">

HTML

echo "Done -> $OUT"

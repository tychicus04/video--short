#!/usr/bin/env bash
# Download fonts and the LaMa model (skips files that exist), then register the fonts with fontconfig so cairosvg finds them.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p assets/fonts models
fetch() { [ -s "$2" ] || curl -fL --retry 3 -o "$2" "$1"; }
fetch https://github.com/google/fonts/raw/main/ofl/patrickhand/PatrickHand-Regular.ttf assets/fonts/PatrickHand-Regular.ttf
fetch https://github.com/google/fonts/raw/main/ofl/bevietnampro/BeVietnamPro-Bold.ttf assets/fonts/BeVietnamPro-Bold.ttf
fetch https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt models/big-lama.pt
mkdir -p ~/.local/share/fonts/vshort
cp assets/fonts/*.ttf ~/.local/share/fonts/vshort/
fc-cache -f

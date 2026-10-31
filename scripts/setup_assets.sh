#!/usr/bin/env bash
# Download fonts and the LaMa model; skips files that already exist.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p assets/fonts models
fetch() { [ -s "$2" ] || curl -fL --retry 3 -o "$2" "$1"; }
for w in Bold ExtraBold; do
  fetch "https://github.com/google/fonts/raw/main/ofl/bevietnampro/BeVietnamPro-$w.ttf" "assets/fonts/BeVietnamPro-$w.ttf"
done
fetch https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt models/big-lama.pt

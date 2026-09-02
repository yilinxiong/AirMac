#!/bin/bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_ICON="${PROJECT_DIR}/icon.png"
OUTPUT_DIR="${PROJECT_DIR}/icons"
TEMP_DIR="$(mktemp -d)"

cleanup() {
    rm -rf "${TEMP_DIR}"
}
trap cleanup EXIT

mkdir -p "${OUTPUT_DIR}"
sips -z 180 180 "${SOURCE_ICON}" --out "${OUTPUT_DIR}/apple-touch-icon.png"
sips -z 192 192 "${SOURCE_ICON}" --out "${OUTPUT_DIR}/icon-192.png"
sips -z 512 512 "${SOURCE_ICON}" --out "${OUTPUT_DIR}/icon-512.png"

# Crop away the legacy white corners, reduce the artwork into the standard
# maskable safe zone, then place it on an opaque full-bleed background.
sips -c 860 860 "${SOURCE_ICON}" --out "${TEMP_DIR}/maskable-crop.png"
sips -z 390 390 "${TEMP_DIR}/maskable-crop.png" --out "${TEMP_DIR}/maskable-small.png"
sips -p 512 512 --padColor 050505 "${TEMP_DIR}/maskable-small.png" \
    --out "${OUTPUT_DIR}/icon-maskable-512.png"

#!/bin/bash
# Build ready-to-boot Sony Xperia XZ (kagura) iOS 16 boot image: kagura-boot.img
# Usage:
#   ./tools/build-kagura-boot.sh STOCK_XPERIA_XZ_BOOT.img KERNEL_MACHO [VENDOR_FIRMWARE_DIR]
set -euo pipefail
if [ $# -lt 2 ]; then
    echo "Usage: $0 <stock-kagura-boot.img> <kernel.development.sweet> [vendor-firmware-dir]" >&2
    exit 1
fi

REPO=$(cd "$(dirname "$0")/.." && pwd)
STOCK=$(realpath "$1")
KERNEL=$(realpath "$2")
FW_DIR=${3:-}

OUT_DIR="$REPO/shim/out"
mkdir -p "$OUT_DIR"

echo "[1/3] Generating Sony Xperia XZ (kagura) Apple Device Tree (ADT)..."
python3 "$REPO/tools/mkadt.py" "$OUT_DIR/kagura.adt" --kagura

BLOB_ARGS=()
if [ -n "$FW_DIR" ] && [ -d "$FW_DIR" ]; then
    [ -f "$FW_DIR/pm4.bin" ] && BLOB_ARGS+=(--blob "GPU-PM4=$FW_DIR/pm4.bin")
    [ -f "$FW_DIR/pfp.bin" ] && BLOB_ARGS+=(--blob "GPU-PFP=$FW_DIR/pfp.bin")
    [ -f "$FW_DIR/a530_zap.mdt" ] && BLOB_ARGS+=(--blob "GPU-ZAP-MDT=$FW_DIR/a530_zap.mdt")
    [ -f "$FW_DIR/a530_zap.b02" ] && BLOB_ARGS+=(--blob "GPU-ZAP-SEG=$FW_DIR/a530_zap.b02")
fi

GPU_MODE=0
if [ ${#BLOB_ARGS[@]} -ge 4 ]; then
    GPU_MODE=8
fi

ARGS="debug=0xc serial=3 cpus=4 keepsyms=1 -noprogress sweetusb=0 rd=ufsroot0 unentitled_ios_sim_launch=1 ignition_level=1 wdt_test=no_user_checkin ufsrw=1 rootrw=1 launchd_unsecure_cache=1 wdt=-1 sweetfb_noconsole=1 sweetsample=- sweetnull=backboardd cs_enforcement_disable=1 sweetprof=- sweetgpu=${GPU_MODE} sweetddr=1804"

echo "[2/3] Packing XNU kernel + kagura.adt into SWEETXNU payload..."
python3 "$REPO/tools/mkpayload.py" "$KERNEL" "$OUT_DIR/kagura.adt" "$OUT_DIR/kagura-payload.bin" \
    --cmdline "$ARGS" "${BLOB_ARGS[@]}"

echo "[3/3] Building kagura shim and wrapping into $OUT_DIR/kagura-boot.img..."
WDT_SECS=0 "$REPO/shim/build-pixel.sh" "$STOCK" "$OUT_DIR/kagura-payload.bin"
cp "$OUT_DIR/pixel-boot.img" "$OUT_DIR/kagura-boot.img"
echo "Done! Test without flashing via: fastboot boot $OUT_DIR/kagura-boot.img"

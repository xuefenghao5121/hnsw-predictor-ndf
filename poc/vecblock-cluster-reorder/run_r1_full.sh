#!/bin/bash
# run_r1_full.sh — R1: full cluster reorder (cross-block) + golden protocol
# POC: vecblock-cluster-reorder
#
# Protocol: CON-SLA-020 sustained, CON-SLA-014 strict cgroup, CON-SLA-019 禁预热
# Configs: cfg-m24-ef60

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
DATA_DIR="$REPO/output/sift1m_m24"
SUDO_STDIN_PASS="${SUDO_STDIN_PASS:-huawei}"

K=${K:-512}

mkdir -p "$BUILD_DIR"

# 1. Build
echo "[Build] full_cluster_reorder"
g++ -O3 -std=c++17 -march=native -fopenmp \
    "$SCRIPT_DIR/full_cluster_reorder.cpp" -o "$BUILD_DIR/full_cluster_reorder"

# 2. Full cluster reorder
OUT_DIR="$BUILD_DIR/full_cluster_k${K}"
if [ ! -f "$OUT_DIR/vecblocks_64k.bin" ]; then
    echo "[Cluster] Full reorder k=$K..."
    "$BUILD_DIR/full_cluster_reorder" 128 \
        "$DATA_DIR/sift1m_m24_vecblocks_64k.bin" \
        "$OUT_DIR" "$K"
else
    echo "[Cluster] Using cached $OUT_DIR"
fi

# 3. Setup test dir - symlink all original files, replace only vecblocks
TEST_DIR="$BUILD_DIR/data_full_k${K}"
mkdir -p "$TEST_DIR"
PREFIX="$TEST_DIR/sift1m_m24"

for f in "$DATA_DIR"/sift1m_m24_*; do
    base=$(basename "$f")
    [[ "$base" == "sift1m_m24_vecblocks_64k.bin" ]] && continue
    [[ "$base" == "sift1m_m24_vecblocks_64k.bin.meta" ]] && continue
    ln -sf "$f" "$TEST_DIR/$base" 2>/dev/null || cp "$f" "$TEST_DIR/$base"
done
ln -sf "$OUT_DIR/vecblocks_64k.bin" "$PREFIX"_vecblocks_64k.bin

echo "[Setup] Test dir: $TEST_DIR"

# 4. Golden protocol: 256MB + 512MB, 1T + 16T (4 scenes)
SCENES=("256 1" "256 16" "512 1" "512 16")

for scene in "${SCENES[@]}"; do
    read -r CG TH <<< "$scene"
    echo ""
    echo "=== Full cluster k=$K ${CG}MB ${TH}T ==="
    SUDO_STDIN_PASS="$SUDO_STDIN_PASS" \
    CGROUP_MB="$CG" THREADS="$TH" \
    DATA_PREFIX="$PREFIX" EF=60 \
    TAG="full_k${K}_${CG}mb_${TH}t" OUTDIR="$BUILD_DIR" \
    bash "$REPO/scripts/run_sustained.sh" 2>&1 | grep -E "===|CSV_AGG"
done

echo ""
echo "=== Golden done ==="

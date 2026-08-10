#!/bin/bash
# run_r0.sh — R0 A/B: original BFS vs within-block cluster-sort vecblocks
# POC: vecblock-cluster-reorder
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
DATA_DIR="$REPO/output/sift1m_m24"

K=${K:-512}


IN_VECBLOCKS="${IN_VECBLOCKS:-$DATA_DIR/sift1m_m24_vecblocks_64k.bin}"
SUDO_STDIN_PASS="${SUDO_STDIN_PASS:-huawei}"

mkdir -p "$BUILD_DIR"

# 1. Build
echo "[Build] cluster_reorder"
g++ -O3 -std=c++17 -march=native -fopenmp \
    "$SCRIPT_DIR/cluster_reorder.cpp" -o "$BUILD_DIR/cluster_reorder"

# 2. Generate cluster-sorted vecblocks
OUT_VECBLOCKS="$BUILD_DIR/cluster_k${K}_vecblocks_64k.bin"
if [ ! -f "$OUT_VECBLOCKS" ]; then
    echo "[Cluster] k=$K, generating cluster-sorted vecblocks..."
    "$BUILD_DIR/cluster_reorder" \
        "128" "$IN_VECBLOCKS" "$OUT_VECBLOCKS" "$K"
else
    echo "[Cluster] Using cached $OUT_VECBLOCKS"
fi

# 3. Setup test dir with cluster vecblocks + symlinked graph files
TEST_DIR="$BUILD_DIR/data_k${K}"
mkdir -p "$TEST_DIR"
PREFIX="$TEST_DIR/sift1m_m24"

# Copy/Link all data files, replacing only vecblocks
for f in "$DATA_DIR"/sift1m_m24_*; do
    base=$(basename "$f")
    # Skip the original vecblocks, we use cluster version
    [[ "$base" == "sift1m_m24_vecblocks_64k.bin" ]] && continue
    [[ "$base" == "sift1m_m24_vecblocks_64k.bin.meta" ]] && continue
    ln -sf "$f" "$TEST_DIR/$base" 2>/dev/null || cp "$f" "$TEST_DIR/$base"
done
# Copy meta if it exists
if [ -f "$IN_VECBLOCKS.meta" ]; then
    cp "$IN_VECBLOCKS.meta" "$OUT_VECBLOCKS.meta"
fi
ln -sf "$OUT_VECBLOCKS" "$PREFIX"_vecblocks_64k.bin

echo "[Setup] Test dir: $TEST_DIR"

# 4. Run A/B
CGROUP_MB=${CGROUP_MB:-256}
THREADS=${THREADS:-1}
EF=${EF:-60}

echo ""
echo "=== R0-A: baseline (BFS-order vecblocks) ==="
SUDO_STDIN_PASS="$SUDO_STDIN_PASS" \
CGROUP_MB="$CGROUP_MB" THREADS="$THREADS" \
DATA_PREFIX="$DATA_DIR/sift1m_m24" EF="$EF" \
TAG="r0_a_bfs_k${K}" OUTDIR="$BUILD_DIR" \
bash "$REPO/scripts/run_sustained.sh" 2>&1 | grep -E "===|CSV_AGG"

echo ""
echo "=== R0-B: cluster-sorted vecblocks (k=$K) ==="
SUDO_STDIN_PASS="$SUDO_STDIN_PASS" \
CGROUP_MB="$CGROUP_MB" THREADS="$THREADS" \
DATA_PREFIX="$PREFIX" EF="$EF" \
TAG="r0_b_cluster_k${K}" OUTDIR="$BUILD_DIR" \
bash "$REPO/scripts/run_sustained.sh" 2>&1 | grep -E "===|CSV_AGG"

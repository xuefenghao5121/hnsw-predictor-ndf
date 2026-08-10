#!/bin/bash
# run_r0.sh — R0: BFS-supervised k-means vs pure k-means
# POC: bfs-cluster
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
DATA_DIR="$REPO/output/sift1m_m24"
GRAPH="$DATA_DIR/sift1m_m24_graph.bin"
IN_VECBLOCKS="$DATA_DIR/sift1m_m24_vecblocks_64k.bin"
SUDO_STDIN_PASS="${SUDO_STDIN_PASS:-huawei}"

K=${K:-1024}
LAMBDA=${LAMBDA:-1.0}

mkdir -p "$BUILD_DIR"

# 1. Build
echo "[Build] bfs_cluster_reorder"
g++ -O3 -std=c++17 -march=native -fopenmp -I"$REPO/include" \
    "$SCRIPT_DIR/bfs_cluster_reorder.cpp" -o "$BUILD_DIR/bfs_cluster_reorder"

# 2. Generate BFS-supervised vecblocks
OUT_VECBLOCKS="$BUILD_DIR/bfs_cluster_k${K}_l${LAMBDA}.bin"
if [ ! -f "$OUT_VECBLOCKS" ]; then
    echo "[BFS-Cluster] k=$K λ=$LAMBDA..."
    "$BUILD_DIR/bfs_cluster_reorder" 128 "$GRAPH" "$IN_VECBLOCKS" "$OUT_VECBLOCKS" "$K" "$LAMBDA"
else
    echo "[BFS-Cluster] Using cached $OUT_VECBLOCKS"
fi

# 3. Setup test dir
TEST_DIR="$BUILD_DIR/data_bfs_k${K}_l${LAMBDA}"
rm -rf "$TEST_DIR" && mkdir -p "$TEST_DIR"
PREFIX="$TEST_DIR/sift1m_m24"

for f in "$DATA_DIR"/sift1m_m24_*; do
    base=$(basename "$f")
    [[ "$base" == "sift1m_m24_vecblocks_64k.bin" ]] && continue
    ln -sf "$(realpath "$f")" "$TEST_DIR/$base"
done
ln -sf "$(realpath "$OUT_VECBLOCKS")" "$PREFIX"_vecblocks_64k.bin

echo "[Setup] Test dir ready"

# 4. Run A/B: pure k-means vs BFS-supervised
echo ""
echo "=== R0-A: pure k-means k=$K ==="
PURE_VECBLOCKS="$REPO/poc/vecblock-cluster-reorder/build/cluster_k${K}_vecblocks_64k.bin"
if [ -f "$PURE_VECBLOCKS" ]; then
    # Use cached pure k-means data
    PURE_DIR="$BUILD_DIR/data_pure_k${K}"
    mkdir -p "$PURE_DIR" && PURE_PREFIX="$PURE_DIR/sift1m_m24"
    for f in "$DATA_DIR"/sift1m_m24_*; do
        base=$(basename "$f")
        [[ "$base" == "sift1m_m24_vecblocks_64k.bin" ]] && continue
        ln -sf "$(realpath "$f")" "$PURE_DIR/$base"
    done
    ln -sf "$(realpath "$PURE_VECBLOCKS")" "$PURE_PREFIX"_vecblocks_64k.bin

    SUDO_STDIN_PASS="$SUDO_STDIN_PASS" CGROUP_MB=256 THREADS=1 \
    DATA_PREFIX="$PURE_PREFIX" EF=60 TAG="r0a_pure_k${K}" OUTDIR="$BUILD_DIR" \
    bash "$REPO/scripts/run_sustained.sh" 2>&1 | grep "CSV_AGG"
else
    echo "  Pure k=$K not cached — using golden baseline: 1,812 QPS"
fi

echo ""
echo "=== R0-B: BFS-supervised k=$K λ=$LAMBDA ==="
SUDO_STDIN_PASS="$SUDO_STDIN_PASS" CGROUP_MB=256 THREADS=1 \
DATA_PREFIX="$PREFIX" EF=60 TAG="r0b_bfs_k${K}_l${LAMBDA}" OUTDIR="$BUILD_DIR" \
bash "$REPO/scripts/run_sustained.sh" 2>&1 | grep "CSV_AGG"

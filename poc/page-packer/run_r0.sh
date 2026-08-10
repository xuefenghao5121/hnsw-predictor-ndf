#!/bin/bash
# run_r0.sh — R0: cluster sort vs cluster+page-pack
# Pipeline: cluster_reorder → shuffle_vecblocks (DEC-018)
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
BUILD_DIR="$REPO/poc/page-packer/build"
DATA_DIR="$REPO/output/sift1m_m24"
GRAPH="$DATA_DIR/sift1m_m24_graph.bin"
BFS="$DATA_DIR/sift1m_m24_bfs.bin"
IN_VB="$DATA_DIR/sift1m_m24_vecblocks_64k.bin"
SUDO="${SUDO_STDIN_PASS:-huawei}"

K=${K:-1024}
mkdir -p "$BUILD_DIR"

# 1. Ensure tools built
cd "$REPO"
make build/cluster_reorder 2>/dev/null || true
make build/shuffle_vecblocks 2>/dev/null || true

# 2. Step 1: cluster sort
CLUSTER_VB="$BUILD_DIR/cluster_k${K}.bin"
if [ ! -f "$CLUSTER_VB" ]; then
    echo "[Step1] cluster_reorder k=$K"
    build/cluster_reorder 128 "$IN_VB" "$CLUSTER_VB" "$K" 2>&1 | tail -3
fi

# 3. Step 2: page packing (shuffle)
PACKED_VB="$BUILD_DIR/packed_k${K}.bin"
if [ ! -f "$PACKED_VB" ]; then
    echo "[Step2] shuffle_vecblocks (page packing)"
    build/shuffle_vecblocks "$GRAPH" "$BFS" "$CLUSTER_VB" "$PACKED_VB" 2>&1 | tail -5
fi

# 4. Setup test dirs + run A/B
for label vb in "A_cluster" "$CLUSTER_VB" "B_packed" "$PACKED_VB"; do
    TEST_DIR="$BUILD_DIR/data_${label}"
    rm -rf "$TEST_DIR" && mkdir -p "$TEST_DIR"
    PREFIX="$TEST_DIR/sift1m_m24"
    for f in "$DATA_DIR"/sift1m_m24_*; do
        base=$(basename "$f")
        [[ "$base" == "sift1m_m24_vecblocks_64k.bin" ]] && continue
        ln -sf "$(realpath "$f")" "$TEST_DIR/$base"
    done
    ln -sf "$(realpath "$vb")" "$PREFIX"_vecblocks_64k.bin

    echo ""
    echo "=== R0-${label}: cluster${label:1:1} ==="
    SUDO_STDIN_PASS="$SUDO" CGROUP_MB=256 THREADS=1 \
    DATA_PREFIX="$PREFIX" EF=60 TAG="r0_${label}" OUTDIR="$BUILD_DIR" \
    bash "$REPO/scripts/run_sustained.sh" 2>&1 | grep "CSV_AGG"
done
echo "=== Done ==="

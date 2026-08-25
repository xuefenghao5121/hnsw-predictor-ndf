#!/usr/bin/env bash
# run_measure_1t.sh — 1T supplementary measure @ locked operating point (beam=32/R0=32/α=1.2)
#
# Supplementary 1T sustained evidence for hierarchical-vamana, same bind:
#   bl-trunk-d0ae5dd × cfg-sla-ef100 × VER-001/003 (cgroup 512MB, THREADS=1)
# Locked config (human override, INTERFACE.md interface_contract):
#   HV_M=16 HV_R0=32 HV_RUP=16 HV_BEAM=32 HV_ALPHA=1.2 HV_ALPHA2=0 HV_ROUNDS=3 HV_SEED=42
#
# Primary protocol remains 16T; this hop supplements THREADS=1 numbers only.
# Build wrapper pins HV_BEAM=32 (and other locked defaults) explicitly because
# vamana_build.cpp still defaults HV_BEAM=64 / HV_ROUNDS=2 (implementation-step landing
# is the next dispatch).
set -uo pipefail
cd /home/huawei/hnsw-predictor-pageann

EV="poc/hierarchical-vamana/ndf/evidence"
mkdir -p "$EV"

TAG="hv_beam32_r0_32"

echo "############################################################"
echo "### 1T SUPPLEMENTARY @ locked beam=32/R0=32/α=1.2"
echo "############################################################"

echo "--- BUILD beam=32 R0=32 α=1.2 (locked) ---"
OMP_NUM_THREADS=24 \
  HV_M=16 HV_R0=32 HV_RUP=16 HV_BEAM=32 HV_ALPHA=1.2 HV_ALPHA2=0 HV_ROUNDS=3 HV_SEED=42 \
  ./poc/hierarchical-vamana/build-bin/vamana_build \
    data/sift_base.fvecs poc/hierarchical-vamana/output/sift1m_graph.bin \
  2>&1 | tee "$EV/build-1t-beam32_r032.log"
BRC=${PIPESTATUS[0]}
if [ "$BRC" -ne 0 ]; then
  echo "!!! BUILD FAILED beam=32 R0=32 (rc=$BRC) — aborting !!!"
  exit 1
fi

echo "--- REORDER + BLOCKS beam=32 R0=32 ---"
./build/bfs_reorder poc/hierarchical-vamana/output/sift1m_graph.bin poc/hierarchical-vamana/output/sift1m_bfs.bin
./build/write_blocks_veconly poc/hierarchical-vamana/output/sift1m_graph.bin poc/hierarchical-vamana/output/sift1m_bfs.bin poc/hierarchical-vamana/output/sift1m_vecblocks_64k.bin 65536
./build/write_blocks poc/hierarchical-vamana/output/sift1m_graph.bin poc/hierarchical-vamana/output/sift1m_bfs.bin poc/hierarchical-vamana/output/sift1m_blocks_64k.bin 65536
./build/gen_route poc/hierarchical-vamana/output/sift1m_blocks_64k.bin poc/hierarchical-vamana/output/sift1m_route_64k.bin

echo "--- MEASURE POC @1T ---"
CGROUP_MB=512 THREADS=1 TAG="$TAG" bash poc/hierarchical-vamana/scripts/run_poc_measure.sh
RC=$?
SRC="results/sustained/${TAG}_512mb_1t_n1000_r15.log"
if [ -f "$SRC" ]; then
  cp "$SRC" "$EV/run_poc_measure-512mb-1t-beam32_r032.log"
  echo "--- copied POC 1T evidence (rc=$RC) ---"
else
  echo "!!! WARNING: missing POC 1T measure log $SRC (rc=$RC) !!!"
fi

echo "--- MEASURE TRUNK bl-trunk-d0ae5dd @1T (reference) ---"
CGROUP_MB=512 THREADS=1 TAG="bl_trunk_d0ae5dd_1t" bash scripts/run_sustained.sh --config cfg-sla-ef100
TRC=$?
TSRC="results/sustained/bl_trunk_d0ae5dd_1t_512mb_1t_n1000_r15.log"
if [ -f "$TSRC" ]; then
  cp "$TSRC" "$EV/run_trunk_measure-512mb-1t.log"
  echo "--- copied TRUNK 1T evidence (rc=$TRC) ---"
else
  echo "!!! WARNING: missing TRUNK 1T measure log $TSRC (rc=$TRC) !!!"
fi

echo ""
echo "=== 1T SUPPLEMENTARY DONE ==="
ls -la "$EV"/run_poc_measure-512mb-1t-beam32_r032.log "$EV"/run_trunk_measure-512mb-1t.log "$EV"/build-1t-beam32_r032.log

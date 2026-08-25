#!/usr/bin/env bash
# run_sweep_r2.sh — R2 beam+R0 sweep @ α=1.2 for hierarchical-vamana
#
# Fixed: HV_M=16 HV_RUP=16 HV_ALPHA=1.2 HV_ROUNDS=3 HV_SEED=42 THREADS=16
# Sweep:
#   beam ∈ {32, 64, 128} at HV_R0=32
#   R0   ∈ {24, 32, 40}  at HV_BEAM=64
# Center point (beam=64, R0=32) is shared by both axes (5 unique configs).
#
# Bind: bl-trunk-d0ae5dd × cfg-sla-ef100 × VER-001/003 (512MB/16T, no 1T).
# Protocol mirror: scripts/run_poc_measure.sh (same-sourced sustained protocol,
# POC BFS-ordered vecblocks).
set -uo pipefail
cd /home/huawei/hnsw-predictor-pageann

EV="poc/hierarchical-vamana/ndf/evidence"
mkdir -p "$EV"

# config list: "beam:R0"
CONFIGS=(
  "32:32"
  "64:32"
  "128:32"
  "64:24"
  "64:40"
)

for CFG in "${CONFIGS[@]}"; do
  BEAM="${CFG%%:*}"
  R0="${CFG##*:}"
  TAG="hv_beam${BEAM}_r0_${R0}"
  echo ""
  echo "############################################################"
  echo "### R2 SWEEP beam=$BEAM R0=$R0 (α=1.2, TAG=$TAG)"
  echo "############################################################"

  echo "--- BUILD beam=$BEAM R0=$R0 ---"
  OMP_NUM_THREADS=24 \
    HV_M=16 HV_R0="$R0" HV_RUP=16 HV_BEAM="$BEAM" HV_ALPHA=1.2 HV_ALPHA2=0 HV_ROUNDS=3 HV_SEED=42 \
    ./poc/hierarchical-vamana/build-bin/vamana_build \
      data/sift_base.fvecs poc/hierarchical-vamana/output/sift1m_graph.bin \
    2>&1 | tee "$EV/build-r2-beam${BEAM}_r0${R0}.log"
  BRC=${PIPESTATUS[0]}
  if [ "$BRC" -ne 0 ]; then
    echo "!!! BUILD FAILED beam=$BEAM R0=$R0 (rc=$BRC) — skipping measure !!!"
    continue
  fi

  echo "--- REORDER + BLOCKS beam=$BEAM R0=$R0 ---"
  ./build/bfs_reorder poc/hierarchical-vamana/output/sift1m_graph.bin poc/hierarchical-vamana/output/sift1m_bfs.bin
  ./build/write_blocks_veconly poc/hierarchical-vamana/output/sift1m_graph.bin poc/hierarchical-vamana/output/sift1m_bfs.bin poc/hierarchical-vamana/output/sift1m_vecblocks_64k.bin 65536
  ./build/write_blocks poc/hierarchical-vamana/output/sift1m_graph.bin poc/hierarchical-vamana/output/sift1m_bfs.bin poc/hierarchical-vamana/output/sift1m_blocks_64k.bin 65536
  ./build/gen_route poc/hierarchical-vamana/output/sift1m_blocks_64k.bin poc/hierarchical-vamana/output/sift1m_route_64k.bin

  echo "--- MEASURE beam=$BEAM R0=$R0 ---"
  CGROUP_MB=512 THREADS=16 TAG="$TAG" bash poc/hierarchical-vamana/scripts/run_poc_measure.sh
  RC=$?

  SRC="results/sustained/${TAG}_512mb_16t_n1000_r15.log"
  if [ -f "$SRC" ]; then
    cp "$SRC" "$EV/run_poc_measure-512mb-16t-r2-beam${BEAM}_r0${R0}.log"
    echo "--- copied evidence: $EV/run_poc_measure-512mb-16t-r2-beam${BEAM}_r0${R0}.log (rc=$RC) ---"
  else
    echo "!!! WARNING: missing measure log $SRC (rc=$RC) !!!"
  fi
done

echo ""
echo "=== R2 SWEEP DONE ==="
ls -la "$EV"/run_poc_measure-512mb-16t-r2-*.log "$EV"/build-r2-*.log

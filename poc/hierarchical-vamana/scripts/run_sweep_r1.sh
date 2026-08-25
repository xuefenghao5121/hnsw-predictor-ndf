#!/usr/bin/env bash
# run_sweep_r1.sh — R1 α-sweep {1.0,1.2,1.4} @ 16T for hierarchical-vamana
set -uo pipefail
cd /home/huawei/hnsw-predictor-pageann

EV="poc/hierarchical-vamana/ndf/evidence"
mkdir -p "$EV"

for ALPHA in 1.0 1.2 1.4; do
  TAG="hv_vamana_a${ALPHA/./_}"
  echo ""
  echo "############################################################"
  echo "### SWEEP alpha=$ALPHA (TAG=$TAG)"
  echo "############################################################"

  echo "--- BUILD alpha=$ALPHA ---"
  OMP_NUM_THREADS=24 \
    HV_M=16 HV_R0=32 HV_RUP=16 HV_BEAM=64 HV_ALPHA="$ALPHA" HV_ALPHA2=0 HV_ROUNDS=3 HV_SEED=42 \
    ./poc/hierarchical-vamana/build-bin/vamana_build \
      data/sift_base.fvecs poc/hierarchical-vamana/output/sift1m_graph.bin \
    2>&1 | tee "$EV/build-alpha${ALPHA}.log"

  echo "--- REORDER + BLOCKS alpha=$ALPHA ---"
  ./build/bfs_reorder poc/hierarchical-vamana/output/sift1m_graph.bin poc/hierarchical-vamana/output/sift1m_bfs.bin
  ./build/write_blocks_veconly poc/hierarchical-vamana/output/sift1m_graph.bin poc/hierarchical-vamana/output/sift1m_bfs.bin poc/hierarchical-vamana/output/sift1m_vecblocks_64k.bin 65536
  ./build/write_blocks poc/hierarchical-vamana/output/sift1m_graph.bin poc/hierarchical-vamana/output/sift1m_bfs.bin poc/hierarchical-vamana/output/sift1m_blocks_64k.bin 65536
  ./build/gen_route poc/hierarchical-vamana/output/sift1m_blocks_64k.bin poc/hierarchical-vamana/output/sift1m_route_64k.bin

  echo "--- MEASURE alpha=$ALPHA ---"
  CGROUP_MB=512 THREADS=16 TAG="$TAG" bash poc/hierarchical-vamana/scripts/run_poc_measure.sh
  RC=$?

  SRC="results/sustained/${TAG}_512mb_16t_n1000_r15.log"
  if [ -f "$SRC" ]; then
    cp "$SRC" "$EV/run_poc_measure-512mb-16t-alpha${ALPHA}.log"
    echo "--- copied evidence: $EV/run_poc_measure-512mb-16t-alpha${ALPHA}.log (rc=$RC) ---"
  else
    echo "!!! WARNING: missing measure log $SRC (rc=$RC) !!!"
  fi
done

echo ""
echo "=== SWEEP DONE ==="
ls -la "$EV"/run_poc_measure-512mb-16t-alpha*.log "$EV"/build-alpha*.log

#!/usr/bin/env bash
# Comprehensive sustained sweep (VER-043 / VER-044 口径)
# 256/512MB × 1/4/8/16T × BASE/ADAPTIVE/GBDT + hnswlib unlimited 对照
set -uo pipefail
REPO=/home/huawei/hnsw-predictor-ndf
cd "$REPO"
export SUDO_STDIN_PASS=huawei

CSV=results/sustained/comprehensive.csv
mkdir -p results/sustained
echo "dataset,cgroup_mb,threads,mode,agg_qps,steady_qps,recall,unique,rss_mb" > "$CSV"

grab() {  # $1=logfile -> "agg,steady,recall,unique"
  # CSV_AGG,rounds,queries,seconds,qps,recall,unique,last_round_qps
  local L="$1"
  awk -F, '/^CSV_AGG/{print $5","$8","$6","$7}' "$L" | tail -1
}

for MB in 512 256; do
  for T in 1 4 8 16; do
    for MODE in base adapt gbdt; do
      EXTRA=""
      case "$MODE" in
        adapt) EXTRA="export ADAPTIVE_EF=1 ADAPTIVE_EASY_GAP=1.006 ADAPTIVE_EASY_EF=50 ADAPTIVE_HARD_GAP=1.002 ADAPTIVE_HARD_EF=200" ;;
        gbdt)  EXTRA="export LEARNED_EF=1 GBDT_MARGIN=0.8" ;;
      esac
      TAG="comp_${MODE}"
      OUT="results/sustained/${TAG}_${MB}mb_${T}t_n1000_r15.log"
      echo ">>> SIFT1M ${MB}MB ${T}T ${MODE}"
      TAG="$TAG" CGROUP_MB=$MB THREADS=$T PER_ROUND=1000 ROUNDS=15 \
        EXTRA="$EXTRA" bash scripts/run_sustained.sh >/dev/null 2>&1
      V=$(grab "$OUT")
      RSS=$(grep -oP 'Final RSS:\s*\K[0-9]+' "$OUT" | tail -1)
      [ -z "$V" ] && V=",,,"
      echo "sift1m,$MB,$T,$MODE,$V,${RSS:-}" >> "$CSV"
      echo "    -> $V"
    done
  done
done

echo ">>> hnswlib unlimited 对照 (VER-044)"
for T in 1 4 8 16; do
  echo "huawei" | sudo -S bash -c "sync; echo 3 > /proc/sys/vm/drop_caches" 2>/dev/null
  OUT="results/sustained/comp_hnswlib_${T}t.log"
  NUM_THREADS=$T ./build/benchmark_hnswlib_native \
    output/sift1m_index.bin data/sift_query_official10k.fvecs \
    data/sift_gt_official10k_k10.bin 10 100 10000 > "$OUT" 2>&1
  Q=$(grep -oP '^QPS:\s*\K[0-9.]+' "$OUT" | tail -1)
  R=$(grep -oP '^Recall:\s*\K[0-9.]+' "$OUT" | tail -1)
  S=$(grep -oP '^RSS:\s*\K[0-9]+' "$OUT" | tail -1)
  echo "sift1m,unlimited,$T,hnswlib,$Q,$Q,$R,10000,$S" >> "$CSV"
  echo "    ${T}T -> $Q QPS / $R% / ${S}MB"
done

echo "=== DONE ==="
column -t -s, "$CSV"

#!/usr/bin/env bash
# Sustained query benchmark runner — CON-SLA-020 金标测试载体
#
# Clauses: BEH-035 (multi-round sampling), API-019 (CLI),
#          CON-SLA-019 (no warmup of measured queries), CON-SLA-020 (baseline),
#          CON-GOLDEN-001 (golden configs)
# Reference semantics: MODEL-SUSTAINED-001 (spec/models/sustained-query-measurement.md)
# Isolation: CON-SLA-014 protocol via API-016 (scripts/cgroup_utils.sh)
# Verification: VER-043
#
# Usage:
#   # Config A (默认, 向后兼容)
#   CGROUP_MB=256 THREADS=1 bash scripts/run_sustained.sh
#
#   # Config C (M=24, EF=60) via --config
#   CGROUP_MB=256 THREADS=1 bash scripts/run_sustained.sh --config cfg-m24-ef60
#
#   # Dry-run (打印参数不执行)
#   bash scripts/run_sustained.sh --config cfg-m24-ef60 --dry-run
#
# Env knobs (override --config values):
#   CGROUP_MB   cgroup memory.max in MB          (default 512)
#   THREADS     NUM_THREADS                      (default 1)
#   PER_ROUND   queries sampled per round        (default 1000)
#   ROUNDS      number of statistics rounds      (default 15)
#   SEED        seed base (round i uses SEED+i)  (default 42)
#   POOL        query pool (standard set only)   (default official 10K)
#   GT          groundtruth (.ivecs or .bin)     (default official)
#   TAG         output log prefix                (default ver043)
#   OUTDIR      results directory                (default results/sustained)
#   EXTRA       extra `export ...` line(s), e.g. ADAPTIVE_EF=1
#   BIN         benchmark binary                 (default build/benchmark_sustained)
#   DATA_PREFIX data file prefix                  (default output/sift1m)
#   EF          search ef parameter               (default 100)
#
# --config <config_id>:
#   从 spec/50-verification/configs/<config_id>.md 读取 data_path 和参数。
#   Env 显式设置优先于 --config 解析值。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# ─── 参数解析 ───────────────────────────────────────────────
CONFIG_ID=""
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)  CONFIG_ID="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

# ─── --config 解析 ──────────────────────────────────────────
# 从 spec/50-verification/configs/<config_id>.md 提取参数。
# 格式: data_path: <path>  +  "| REFINE_EF | <val> |" 等参数表
CONFIG_DATA_PREFIX=""
CONFIG_VECBLOCKS_PATH=""
CONFIG_EF=""
CONFIG_EXTRA=""

if [[ -n "$CONFIG_ID" ]]; then
  CONFIG_FILE="spec/50-verification/configs/${CONFIG_ID}.md"
  if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "ERROR: config file not found: $CONFIG_FILE" >&2
    echo "Available configs:" >&2
    ls spec/50-verification/configs/cfg-*.md 2>/dev/null | sed 's|.*/||;s|\.md||' >&2
    exit 1
  fi

  # 解析 data_path (去除尾部斜杠)
  CONFIG_DATA_PREFIX=$(grep '^> *data_path:' "$CONFIG_FILE" | head -1 | sed 's/.*data_path: *//;s/ *$//;s|/$||')

  # 解析 vecblocks_path (可选; 覆盖默认 ${DATA_PREFIX}_vecblocks_${BLKSUF}.bin)
  CONFIG_VECBLOCKS_PATH=$(grep '^> *vecblocks_path:' "$CONFIG_FILE" | head -1 | sed 's/.*vecblocks_path: *//;s/ *$//')

  # 解析 REFINE_EF
  CONFIG_EF=$(grep '| REFINE_EF |' "$CONFIG_FILE" | head -1 | awk -F'|' '{gsub(/ /,"",$3); print $3}')
  # 如果没有 REFINE_EF，尝试 M_graph 行推导默认 EF
  if [[ -z "$CONFIG_EF" ]]; then
    CONFIG_EF=$(grep '| M_graph |' "$CONFIG_FILE" | head -1 | awk -F'|' '{gsub(/ /,"",$3); print $3}')
    # M_graph=16 -> EF=100, M_graph=24 -> EF=60 (约定)
    case "$CONFIG_EF" in
      16) CONFIG_EF=100 ;;
      24) CONFIG_EF=60 ;;
    esac
  fi

  # 解析 ADAPTIVE 相关参数 -> 生成 EXTRA
  ADAPTIVE_EF_CFG=$(grep '| ADAPTIVE_EF |' "$CONFIG_FILE" | head -1 | awk -F'|' '{gsub(/ /,"",$3); print $3}')
  if [[ "$ADAPTIVE_EF_CFG" == "1" ]]; then
    CONFIG_EXTRA="export ADAPTIVE_EF=1"
    EASY_EF=$(grep '| ADAPTIVE_EASY_EF |' "$CONFIG_FILE" | head -1 | awk -F'|' '{gsub(/ /,"",$3); print $3}')
    [[ -n "$EASY_EF" ]] && CONFIG_EXTRA="$CONFIG_EXTRA ADAPTIVE_EASY_EF=$EASY_EF"
    EASY_GAP=$(grep '| ADAPTIVE_EASY_GAP |' "$CONFIG_FILE" | head -1 | awk -F'|' '{gsub(/ /,"",$3); print $3}')
    [[ -n "$EASY_GAP" ]] && CONFIG_EXTRA="$CONFIG_EXTRA ADAPTIVE_EASY_GAP=$EASY_GAP"
  fi

  # 解析 cluster_k / cluster_input (可选; 用于自动重生成 cluster-sorted vecblocks)
  CONFIG_CLUSTER_K=$(grep '^> *cluster_k:' "$CONFIG_FILE" | head -1 | sed 's/.*cluster_k: *//;s/ *$//')
  CONFIG_CLUSTER_INPUT=$(grep '^> *cluster_input:' "$CONFIG_FILE" | head -1 | sed 's/.*cluster_input: *//;s/ *$//')

  echo "(config: $CONFIG_ID | data=$CONFIG_DATA_PREFIX | ef=$CONFIG_EF${CONFIG_EXTRA:+ | $CONFIG_EXTRA})" >&2
fi
CGROUP_MB="${CGROUP_MB:-512}"
THREADS="${THREADS:-1}"
POOL="${POOL:-data/sift_query_official10k.fvecs}"
GT="${GT:-data/sift_groundtruth_official.ivecs}"
ROUNDS="${ROUNDS:-15}"
PER_ROUND="${PER_ROUND:-1000}"
SEED="${SEED:-42}"
TAG="${TAG:-ver043}"
OUTDIR="${OUTDIR:-results/sustained}"

# --config 提供默认值，env 覆盖优先
if [[ -n "$CONFIG_DATA_PREFIX" ]]; then
  DATA_PREFIX="${DATA_PREFIX:-$CONFIG_DATA_PREFIX}"
else
  DATA_PREFIX="${DATA_PREFIX:-output/sift1m}"
fi

if [[ -n "$CONFIG_EF" ]]; then
  EF="${EF:-$CONFIG_EF}"
else
  EF="${EF:-100}"
fi

# EXTRA 合并: config_extra 作为底，用户 EXTRA 追加
EXTRA="${EXTRA:-$CONFIG_EXTRA}"
# 如果两者都有，拼接
if [[ -n "$CONFIG_EXTRA" && -n "${EXTRA:-}" && "$EXTRA" != "$CONFIG_EXTRA" ]]; then
  EXTRA="$CONFIG_EXTRA $EXTRA"
fi

BIN="${BIN:-build/benchmark_sustained}"

# block size (bytes); winner default 256KB ([[DEC-004]]). Env-overridable so the
# constraint-aware tuner can sweep the block ladder without forking the pipeline.
BS="${BS:-262144}"
BSK=$(( BS / 1024 ))
BLKSUF="${BSK}k"

if [[ $DRY_RUN -eq 1 ]]; then
  echo "=== DRY RUN ==="
  echo "CONFIG_ID:    ${CONFIG_ID:-<none>}"
  echo "BIN:          $BIN"
  echo "DATA_PREFIX:  $DATA_PREFIX"
  echo "VEC_BLOCKS:   ${CONFIG_VECBLOCKS_PATH:-${DATA_PREFIX}_vecblocks_${BLKSUF}.bin}"
  echo "EF:           $EF"
  echo "CGROUP_MB:    $CGROUP_MB"
  echo "THREADS:      $THREADS"
  echo "ROUNDS:       $ROUNDS"
  echo "PER_ROUND:    $PER_ROUND"
  echo "SEED:         $SEED"
  echo "POOL:         $POOL"
  echo "GT:           $GT"
  echo "TAG:          $TAG"
  echo "OUTDIR:       $OUTDIR"
  echo "EXTRA:        ${EXTRA:-<none>}"
  echo "FVC:          $([ "$CGROUP_MB" -le 256 ] && echo 64 || echo 160)"
  exit 0
fi

# ─── cluster-sorted vecblocks 自动重生成 (BEH-037 可复现性) ──
# 若 config 声明了 cluster_k + cluster_input + vecblocks_path，
# 在测量前自动重生成 cluster-sorted 文件，保证 NVMe 物理布局连续。
# 5 分钟内已生成过则跳过 (避免金标 12 runs 重生成 12 次)
if [[ -n "${CONFIG_CLUSTER_K:-}" && -n "${CONFIG_CLUSTER_INPUT:-}" && -n "${CONFIG_VECBLOCKS_PATH:-}" ]]; then
  CLUSTER_TS_FILE="/tmp/.cluster_reorder_${CONFIG_CLUSTER_K}.ts"
  CLUSTER_AGE=99999
  [[ -f "$CLUSTER_TS_FILE" ]] && CLUSTER_AGE=$(( $(date +%s) - $(stat -c %Y "$CLUSTER_TS_FILE") ))
  if [[ "$CLUSTER_AGE" -gt 300 ]]; then
    if [[ -x build/cluster_reorder ]]; then
      echo "[Cluster] Regenerating k=$CONFIG_CLUSTER_K from $CONFIG_CLUSTER_INPUT..." >&2
      build/cluster_reorder 128 "$CONFIG_CLUSTER_INPUT" "$CONFIG_VECBLOCKS_PATH" "$CONFIG_CLUSTER_K" >&2
      touch "$CLUSTER_TS_FILE"
    else
      echo "[Cluster] WARNING: build/cluster_reorder not found, skipping regeneration" >&2
    fi
  else
    echo "[Cluster] Skipping regeneration (${CLUSTER_AGE}s < 300s since last gen)" >&2
  fi
fi

if [ ! -x "$BIN" ]; then
  echo "ERROR: $BIN not found. Run: make $(basename $BIN)" >&2
  exit 1
fi

# BEH-035: sampling pool MUST be a standard query set, MUST NOT be sampled from base.
case "$POOL" in
  *base*) echo "ERROR: pool looks base-derived ($POOL) — violates BEH-035" >&2; exit 1 ;;
esac

OUT="${OUTDIR}/${TAG}_${CGROUP_MB}mb_${THREADS}t_n${PER_ROUND}_r${ROUNDS}.log"
mkdir -p "$(dirname "$OUT")"

# CON-SLA-016/017/018 measurement convention for flat-vec cache sizing.
FVC=160
[ "$CGROUP_MB" -le 256 ] && FVC=64

# 确定对照基线
BASELINE_ID="bl-trunk-golden-434c6f5"

sudo -n true 2>/dev/null || echo "(sudo password may be required for cgroup + drop_caches)" >&2

SUDO=(sudo)
if [ -n "${SUDO_STDIN_PASS:-}" ]; then
  SUDO=(sudo -S)
fi

"${SUDO[@]}" bash -c "
set -uo pipefail
source $REPO/scripts/cgroup_utils.sh
cg_init sqb_${TAG}_${CGROUP_MB}_${THREADS}_${PER_ROUND} $CGROUP_MB
cg_create
cg_set_limit $CGROUP_MB
cg_drop_caches                      # CON-SLA-014 step 1
cg_add_proc \$\$                     # CON-SLA-014 step 2
cd $REPO
export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
export VEC_BLOCKS_PATH=${VEC_BLOCKS_PATH:-${DATA_PREFIX}_vecblocks_${BLKSUF}.bin}
# Apply config vecblocks_path override (e.g. cluster-sorted, BEH-037)
if [[ -n "${CONFIG_VECBLOCKS_PATH:-}" ]]; then
  export VEC_BLOCKS_PATH="${CONFIG_VECBLOCKS_PATH}"
fi
export PQ_CODES_PATH=${PQ_CODES_PATH:-output/pqco_sift1m_M32_correct.bin}
export REFINE_EF=$EF EVICT_PAGE_CACHE=0 NUM_THREADS=$THREADS
export FLAT_VEC_MB=$FVC PAGE_MERGE_BG=1 L4_WILLNEED=1 WILLNEED_BG=1 VL_POOL_THREADS=14
${EXTRA:-}
# CON-SLA-019: --warmup omitted => 0 => no warmup over measured queries.
$BIN \
  ${DATA_PREFIX}_graph.bin ${DATA_PREFIX}_bfs.bin \
  ${DATA_PREFIX}_blocks_${BLKSUF}.bin ${DATA_PREFIX}_route_${BLKSUF}.bin \
  data/sift_base.fvecs $POOL $GT \
  10 $EF --rounds $ROUNDS --per-round $PER_ROUND --seed $SEED --verbose
# CON-SLA-014 steps 4-5: cgroup accounting evidence
echo '--- cgroup accounting (CON-SLA-014) ---'
cg_stats_summary 2>/dev/null || true
cg_check_violations 2>/dev/null || true
" > "$OUT" 2>&1 < <(printf '%s\n' "${SUDO_STDIN_PASS:-}")
RC=$?

# 输出结果摘要，标注 config + baseline
CONFIG_TAG="${CONFIG_ID:-default}"
echo "=== $TAG | $CONFIG_TAG | $BASELINE_ID | ${CGROUP_MB}MB | ${THREADS}T | N=$PER_ROUND | R=$ROUNDS | seed=$SEED ==="
grep -E "^QPS:|^Recall@|^Round 1 QPS|^Round .* QPS:|^Ramp-up:|^Cumulative|^CSV_AGG" "$OUT" || {
  echo "(no result lines; rc=$RC) tail:"; tail -15 "$OUT"
}
echo "--- log: $OUT"
exit $RC

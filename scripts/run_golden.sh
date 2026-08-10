#!/bin/bash
# run_golden.sh — CON-GOLDEN-001 性能金标自动化 (三配置)
#
# Clauses: CON-GOLDEN-001, CON-SLA-020, CON-SLA-019, CON-SLA-014
# Configs: cfg-sla-ef100 (A), cfg-adaptive-ef90 (B), cfg-m24-ef60 (C)
#
# 用法:
#   sudo bash scripts/run_golden.sh              # 全部三配置 × 4 场景 × 3 轮
#   sudo bash scripts/run_golden.sh --config cfg-m24-ef60  # 单配置
#   SUDO_STDIN_PASS=<pass> bash scripts/run_golden.sh      # 免交互 sudo
#
# 输出: /tmp/golden/*.log + 汇总到 stdout

set -uo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"

# ─── 参数解析 ───
GOLDEN_CONFIGS=(cfg-sla-ef100 cfg-adaptive-ef90 cfg-m24-ef60)
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) GOLDEN_CONFIGS=("$2"); shift 2 ;;
    *) echo "Unknown: $1" >&2; exit 1 ;;
  esac
done

BINDIR=${BINDIR:-build}
MINDIR=/tmp/golden
mkdir -p "$MINDIR"

SUDO=(sudo)
if [ -n "${SUDO_STDIN_PASS:-}" ]; then
  SUDO=(sudo -S)
fi

# 场景矩阵: cgroup × threads
SCENES=("256 1" "256 16" "512 1" "512 16")
RUNS=3

run_one() {
  local CG=$1 NT=$2 CFG=$3 RUN=$4
  local TAG="${CFG}_${CG}mb_${NT}t_r${RUN}"

  "${SUDO[@]}" bash -c "
    set -uo pipefail
    source $REPO/scripts/cgroup_utils.sh
    cg_init gold_${TAG} $CG; cg_create; cg_set_limit $CG
    cg_drop_caches; cg_add_proc \$\$
    cd $REPO
  " < <(printf '%s\n' "${SUDO_STDIN_PASS:-}") 2>/dev/null

  CGROUP_MB=$CG THREADS=$NT TAG=$TAG OUTDIR=$MINDIR \
    CONFIG_GOLDEN=1 \
    "${SUDO[@]}" bash -c "
      cd $REPO
      source scripts/cgroup_utils.sh
      cg_init gold_${TAG} $CG; cg_create; cg_set_limit $CG
      cg_drop_caches; cg_add_proc \$\$
      export CGROUP_MB=$CG THREADS=$NT
      export OUTDIR=$MINDIR TAG=$TAG
      export SUDO_STDIN_PASS='${SUDO_STDIN_PASS:-}'
      bash scripts/run_sustained.sh --config $CFG
    " < <(printf '%s\n' "${SUDO_STDIN_PASS:-}") >/dev/null 2>&1

  local LOG="$MINDIR/${TAG}_${CG}mb_${NT}t_n1000_r15.log"
  echo -n "$CFG ${CG}MB ${NT}T R$RUN: "
  grep "CSV_AGG" "$LOG" 2>/dev/null | tail -1 | awk -F, '{printf "agg=%-8s steady=%-8s recall=%s%%\n",$5,$8,$6}' || echo "(no result)"
}

echo "=== Golden Baseline — Trunk $(git rev-parse --short HEAD) ==="
echo "Configs: ${GOLDEN_CONFIGS[*]}"
echo "Scenes: ${SCENES[*]}"
echo ""

for CFG in "${GOLDEN_CONFIGS[@]}"; do
  echo "--- $CFG ---"
  for SCENE in "${SCENES[@]}"; do
    read -r CG NT <<< "$SCENE"
    for RUN in $(seq 1 $RUNS); do
      run_one "$CG" "$NT" "$CFG" "$RUN"
    done
  done
  echo ""
done
echo "=== DONE ==="

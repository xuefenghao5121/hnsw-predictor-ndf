#!/usr/bin/env bash
# R0 contrast workspace helper for hotspot-optimization (poc_prepare_baseline).
#
# Builds the topic-local sustained binary from unmodified Trunk copies.
# Default is --dry-run of the golden Measure entry (cfg-m24-ef60).
# This hop MUST NOT write PERF_BASELINE Numbers.
#
# Usage:
#   bash poc/hotspot-optimization/run_r0.sh
#   RUN_MEASURE=1 bash poc/hotspot-optimization/run_r0.sh   # later poc_measurement only
set -euo pipefail

TOPIC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$TOPIC_DIR/../.." && pwd)"
BIN="$TOPIC_DIR/build/benchmark_sustained"

cd "$TOPIC_DIR"
make -j"$(nproc)"

if [[ "${RUN_MEASURE:-0}" == "1" ]]; then
  echo "RUN_MEASURE=1: invoking golden Measure. Numbers still belong in poc_measurement." >&2
  CGROUP_MB="${CGROUP_MB:-256}" THREADS="${THREADS:-1}" \
    BIN="$BIN" TAG="${TAG:-hotspot_r0}" \
    bash "$REPO/scripts/run_sustained.sh" --config cfg-m24-ef60
else
  echo "=== hotspot-optimization R0 contrast (dry-run; no Numbers) ===" >&2
  BIN="$BIN" CGROUP_MB="${CGROUP_MB:-256}" THREADS="${THREADS:-1}" \
    TAG="${TAG:-hotspot_r0}" \
    bash "$REPO/scripts/run_sustained.sh" --config cfg-m24-ef60 --dry-run
  echo "Binary: $BIN" >&2
  echo "To measure later: RUN_MEASURE=1 bash poc/hotspot-optimization/run_r0.sh" >&2
fi

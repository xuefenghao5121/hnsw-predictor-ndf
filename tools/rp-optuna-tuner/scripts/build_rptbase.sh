#!/usr/bin/env bash
# build_rptbase.sh — rp-optuna-tuner RP base graph build ([[ARCH-010]]).
#
# Builds the RP denser base graph (beam=64 / α=1.2, M=16 R0=40 Rup=16 rounds=3
# seed=42) into a SEPARATE prefix (default `sift1m_rptbase`) — the default
# `output/sift1m_*` artifact is NOT touched. Delegates to Trunk
# `scripts/build_pipeline.sh` ([[BEH-028]] reuse discipline): no forked search engine,
# no forked pipeline.
#
# Usage:
#   bash tools/rp-optuna-tuner/scripts/build_rptbase.sh [prefix] [pq_M]
#
# This is 1 rebuild against RPT_BUDGET_REBUILDS (14).
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"

PREFIX="${1:-sift1m_rptbase}"
M="${2:-64}"

# RP base graph knobs (DESIGN §Implementation slice / INTERFACE RPT_BASE_GRAPH):
# beam=64 / α=1.2 denser base (winner default graph).
export HV_M=16 HV_R0=40 HV_RUP=16 HV_BEAM=64 HV_ALPHA=1.2 HV_ALPHA2=0 HV_ROUNDS=3 HV_SEED=42

echo "=== RP base graph build (delegated to scripts/build_pipeline.sh): prefix=$PREFIX beam=64 alpha=1.2 M=$M ==="
bash scripts/build_pipeline.sh data/sift_base.fvecs "$PREFIX" "$M"
echo "=== RP base graph build done ==="

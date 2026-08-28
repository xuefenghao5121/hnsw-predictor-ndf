#!/usr/bin/env bash
# run_rp_sustained.sh — rp-optuna-tuner sustained measurement carrier for NON-default
# artifacts ([[ARCH-010]] / [[BEH-029]]).
#
# Thin wrapper over Trunk `scripts/run_sustained.sh` (VER-001 sustained + VER-003 cgroup
# v2): delegates measurement to Trunk's `benchmark_sustained`, parameterised by explicit
# data paths so the RP base graph (S1) and RP-pruned graphs (S2) can be measured WITHOUT
# the `cfg-sla-ef100` config's hardcoded vecblocks_path pinning to the default artifact.
# No forked search engine — the Trunk `build/benchmark_sustained` binary is used (unless
# BIN is overridden for the per-artifact GBDT on-leg, which is the documented exception
# in run_gbdt_probe.sh, [[BEH-029]]).
#
# Env (same names as run_sustained.sh where applicable):
#   DATA_PREFIX       artifact file prefix (default output/sift1m)
#   VEC_BLOCKS_PATH   flat-vec cache blocks   (default ${DATA_PREFIX}_vecblocks_${BLKSUF}.bin)
#   PQ_CODES_PATH     PQ codes                (default output/pqco_sift1m_M64_correct.bin)
#   BS                block size bytes        (default 262144)
#   EF                search ef               (default 100)
#   EXTRA             extra `export ...`      (e.g. LEARNED_EF=1 GBDT_MARGIN=1.3)
#   CGROUP_MB THREADS ROUNDS PER_ROUND SEED TAG OUTDIR BIN POOL GT
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"

# block-size closed ladder guard (inherited from CAT / INTERFACE.md)
BS="${BS:-262144}"
case "$BS" in
  32768|65536|131072|262144) ;;
  *) echo "ERROR: BS=$BS invalid (closed ladder {32768,65536,131072,262144})" >&2; exit 2 ;;
esac

exec bash scripts/run_sustained.sh "$@"

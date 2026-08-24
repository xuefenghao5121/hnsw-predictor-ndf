# R0 remeasure attempt — cluster-gbdt (2026-08-14)

> run_id: run-repair-poc-measurement-cluster-gbdt-20260814T082223Z
> episode_id: ep-repair-poc-measurement-cluster-gbdt-20260814T082100Z
> manifest_sha: ab9e653fbaeb85f83ef5a9d08c5de5f13914a8ff18101f6080004375db4ecc71
> context_plan_sha: b574dbd5c7cad0d98d664981302b2817a2f1f05bf7f22b0db3297dd5c991c653
> base_sha: a14339234133cc6c5a2348464954f744c6465efb
> bind: vs=bl-trunk-golden-7ee4ee2 config_id=cfg-m24-ef60 measure_script=scripts/run_sustained.sh

## Result

**FAILED** — CON-SLA-014 cgroup measurement requires interactive `sudo` (drop_caches + memory limit).
`sudo -n true` returns "需要密码" in this environment; benchmark exited rc=1 before any QPS lines.

## Steps completed

1. Cluster-sorted vecblocks regenerated (k=1024) → `output/sift1m_m24/sift1m_m24_vecblocks_64k_cluster1024.bin`
2. Command attempted:
   `CGROUP_MB=512 THREADS=1 TAG=cluster-gbdt-r0-512mb bash scripts/run_sustained.sh --config cfg-m24-ef60`
3. Log: `poc/cluster-gbdt/ndf/evidence/r0-remeasure-512mb-20260814.log` (sudo failure only)

## Prior logs (not bound as verified)

| log | vecblocks | rounds | note |
|-----|-----------|--------|------|
| `results/sustained/ver043_512mb_1t_n1000_r15.log` | default blocks_64k | 15 | no cluster1024 path; no lease |
| `results/sustained/ver043_256mb_1t_n1000_r15.log` | default blocks_64k | 15 | no cluster1024 path; no lease |
| `results/sustained/verify_cluster_c_256mb_1t_n1000_r3.log` | cluster1024 | 3 | incomplete protocol (R=3) |

PERF_BASELINE claimed numbers remain **unverified**; `baseline_status` stays **stale**.

## Unblock

Run with passwordless sudo for `scripts/cgroup_utils.sh` / drop_caches, or provide `SUDO_STDIN_PASS` in a secure runner, then re-dispatch `poc_measurement`.

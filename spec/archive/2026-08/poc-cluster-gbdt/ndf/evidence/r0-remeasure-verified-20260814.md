# R0 remeasure verified — cluster-gbdt (2026-08-14)

> run_id: run-repair-poc-measurement-cluster-gbdt-20260814T083515Z
> episode_id: ep-repair-poc-measurement-cluster-gbdt-20260814T083515Z
> session_id: d21779ab-aad3-408c-a717-f871eae0884e
> manifest_sha: be0b56edf04118db8bfb392329f2cb089bc564c47852c92caa04bc9717bb80a6
> context_plan_sha: 5794508eb3428b558d777804f24f70821f73bbb8c43d8585082850dcf9670ebf
> base_sha: a14339234133cc6c5a2348464954f744c6465efb
> worktree: .worktrees/cluster-gbdt-measurement-20260814T083515Z
> branch: poc/cluster-gbdt-measurement-20260814T083515Z
> bind: vs=bl-trunk-golden-7ee4ee2 config_id=cfg-m24-ef60 measure_script=scripts/run_sustained.sh
> protocol: CON-SLA-014 + CON-SLA-020 sustained

## Result

**VERIFIED** — full 15×1000 official-pool rounds completed for 512MB and 256MB.
`sudo -n` was available. Cluster k=1024 vecblocks were regenerated immediately before the 512MB run.
The benchmark process aborted in teardown (SIGABRT / wrapper rc=134) after printing aggregate and CSV_AGG; numbers below are taken from those printed lines.

## Commands

```bash
CGROUP_MB=512 THREADS=1 TAG=cluster-gbdt-r0-512mb \
  OUTDIR=poc/cluster-gbdt/ndf/evidence \
  bash scripts/run_sustained.sh --config cfg-m24-ef60
CGROUP_MB=256 THREADS=1 TAG=cluster-gbdt-r0-256mb \
  OUTDIR=poc/cluster-gbdt/ndf/evidence \
  bash scripts/run_sustained.sh --config cfg-m24-ef60
```

## Logs

| log | cgroup | aggregate QPS | steady R4-15 | recall@10 | RSS | FVC |
|-----|--------|--------------:|-------------:|----------:|----:|----:|
| `cluster-gbdt-r0-512mb_512mb_1t_n1000_r15.log` | 512MB | 2248.7 | 2539 σ=90 | 96.59% | 332 MB | 160 |
| `cluster-gbdt-r0-256mb_256mb_1t_n1000_r15.log` | 256MB | 1805.2 | 2042 σ=41 | 96.60% | 231 MB | 64 |

CSV_AGG 512MB: `15,15000,6.670649,2248.7,96.59,7942,2662.9`
CSV_AGG 256MB: `15,15000,8.309433,1805.2,96.60,7942,2062.6`

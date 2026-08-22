# R0 Measurement — hotspot-optimization

> topic: hotspot-optimization
> date: 2026-08-21
> episode: ep-93fcfbef-fce3-4d37-8f7e-eabc349cc4ac
> attempt: ca511456-6886-4bbe-9a2c-c27f0ee65be2
> measured_trunk_sha: f7901cc18dd5ac707303b656a6a284918821f13c
> config: cfg-m24-ef60 (M_graph=24, REFINE_EF=60, FLAT_VEC_MB=64)
> protocol: CON-SLA-014 strict cgroup + CON-SLA-019 禁预热 + CON-SLA-020 sustained

## Command

```bash
bash scripts/run_sustained.sh --config cfg-m24-ef60
```

Cluster-sorted vecblocks regenerated before measurement (k=1024, 7937 blocks, 432443 cluster switches).

## Numbers

| metric | value |
|--------|------:|
| aggregate QPS | 2221.4 |
| steady QPS (Round 15) | 2679.3 |
| Recall@10 | 96.59% |
| RSS | 332 MB |
| ramp-up (R1→R15) | 171.7% |
| cumulative unique queries | 7942 / 10000 |
| total time (15K queries) | 6.752 s |

## Per-round

```
Round  1: QPS=   986.0  recall=96.49%
Round  2: QPS=  2100.0  recall=96.53%
Round  3: QPS=  2206.5  recall=96.33%
Round  4: QPS=  2328.0  recall=96.70%
Round  5: QPS=  2353.6  recall=96.63%
Round  6: QPS=  2398.9  recall=96.37%
Round  7: QPS=  2376.5  recall=96.75%
Round  8: QPS=  2475.8  recall=96.19%
Round  9: QPS=  2502.4  recall=97.03%
Round 10: QPS=  2566.0  recall=96.73%
Round 11: QPS=  2457.6  recall=96.93%
Round 12: QPS=  2617.3  recall=96.10%
Round 13: QPS=  2594.2  recall=97.03%
Round 14: QPS=  2660.7  recall=96.57%
Round 15: QPS=  2679.3  recall=96.54%
CSV_AGG,15,15000,6.752404,2221.4,96.59,7942,2679.3
```

## Teardown

Benchmark printed the full 15 rounds + aggregate, then aborted in teardown with SIGABRT
(rc=134, "terminate called without an active exception"). Numbers are taken from the
printed aggregate and CSV_AGG, consistent with prior verified measurements on the same
benchmark binary.

## Files

- Log: `results/sustained/ver043_512mb_1t_n1000_r15.log`

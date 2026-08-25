# Golden Baseline Index

> thin index → current bl-* + cfg-*；见 baselines/README.md 与 [[VER-005]] / [[META-006]]。

现行 Trunk 金标: **bl-trunk-d9122d2**

| 代码 | 配置 | 基线 |
|------|------|------|
| `d9122d266a33e11a033e4c3a02589e9c2359ab2b` | cfg-sla-ef100 | bl-trunk-d9122d2 |

## 最佳性能速览

| 场景 | Recall@10 | agg QPS | steady QPS | RSS init | RSS end |
|------|----------:|--------:|-----------:|---------:|--------:|
| SIFT1M @ 512MB @ 16T（cfg-sla-ef100） | 97.02% | 5708.4 | 9035.3 | 170 MB | 367 MB |

> 本页为金标索引；数字正文见 `baselines/bl-trunk-d9122d2.md`（非 stable must SLA，见 [[CON-POC-001]]）。

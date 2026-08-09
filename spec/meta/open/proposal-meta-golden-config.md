# Proposal: Process — 最佳配置金标条款 CON-GOLDEN-001

> track: process
> Status: Implemented on 2026-08-09
> 日期: 2026-08-09
> scope: ndf-process

## 背景

性能测试不仅依赖代码，还依赖配置参数。当前最佳配置散落在 DEC-086/DEC-087 的正文和 API-011 的推荐注释中，没有一个统一的"当前最佳配置"快照。

每次 POC/promote 后重跑基线时，需要同时验证：
1. 代码 SHA 是否匹配
2. 配置参数是否匹配
3. 性能数字是否在金标容差内

## 提议

新增产品约束条款 **CON-GOLDEN-001**（spec/40-constraints/），定义：
- 三组标准测试配置（SLA / DEC-086 优化 / DEC-087 Pareto）
- 每组的完整环境变量快照
- 对应的金标性能数据（引用 spec/50-verification/golden-baseline.md）
- 更新触发条件

新增流程条款 **META-006**（spec/meta/），定义：
- POC/promote 后的金标更新义务
- 金标更新必须包含代码 SHA + 配置 + 性能三要素

## 条款草案

### CON-GOLDEN-001 (产品约束)

```markdown
## 性能金标配置 {#CON-GOLDEN-001}
<!-- ndf: kind=constraint level=must layer=L1 status=stable since=0.9.11 -->
<!-- ndf: depends-on=CON-SLA-020,API-011,API-012,API-013,API-017,DEC-086,DEC-087 -->

性能金标由三组标准配置组成。每次主线性能测试 MUST 同时测试三组配置，
并对照 spec/50-verification/golden-baseline.md 的金标数据验证无回归。

### 配置 A: SLA 基线 (CON-SLA-020)
（保守配置，recall 优先）

M=16, EF=100, ADAPTIVE_EF=0

### 配置 B: DEC-086 优化 (sustained 调参)
（均衡配置，QPS/recall 平衡）

M=16, EF=90, ADAPTIVE_EF=1, ADAPTIVE_EASY_EF=40, ADAPTIVE_EASY_GAP=1.006

### 配置 C: DEC-087 Pareto 最优 (pipeline 调参)
（激进配置，QPS 优先，recall 余量最小）

M=24, EF=60, ADAPTIVE_EF=0

### 金标更新触发条件
1. Trunk src/ 代码变更（promote/bug/refactor）
2. 管线参数变更（M_graph / PQ_M / block_size 重建）
3. 新的 DEC 调参结论 promote

### 回归判定
agg/steady QPS 落在金标 ±2CV 内 = 无回归。
Recall 下降 > 0.3pp = 回归。
```

### META-006 (流程)

```markdown
## 金标更新义务 {#META-006}
<!-- ndf: kind=req level=must scope=ndf-process -->

每次 promote / bug / refactor 合入 Trunk src/ 后，MUST：

1. 更新 spec/50-verification/golden-baseline.md
   - 新 Trunk SHA
   - 重跑三组配置（A/B/C）× 2 cgroup × 2 线程数 = 12 数据点
   - 每数据点至少 2 轮
2. 如有配置参数变更，同步更新 CON-GOLDEN-001 的配置快照
3. 金标更新 commit MUST 引用触发的 promote/bug 提案
```

## 影响范围

| 文件 | 操作 |
|------|------|
| spec/40-constraints/sla.md | 新增 CON-GOLDEN-001 段落 |
| spec/meta/process.md | 新增 META-006 段落 |
| spec/50-verification/golden-baseline.md | 引用，不改动 |
| spec/INDEX.md + graph.json | 自动重建 |

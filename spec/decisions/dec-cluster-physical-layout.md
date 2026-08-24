# DEC: Cluster-Sorted Vecblocks 物理布局依赖

> id: DEC-cluster-physical-layout
> date: 2026-08-11
> status: accepted
> related: BEH-037, META-006
> track: process

## 背景

BEH-037 cluster sort (k=1024) 在 POC R2 中报告 +23.4% @1T / +50.8% @16T。
金标重跑（3 轮 mean）只测出 +2.6% / +8.9%，差距 15-40pp。

## 根因

### 现象

- 重新做 k-means 生成新文件后，金标恢复到 +18.5% / +56.2%（与 POC R2 一致）
- 旧文件和新文件 md5 完全相同（`5aadec7c125b60c9a22e5b797aa6b5e8`）
- 原始 vecblocks 文件修改时间 Aug 7，从未被覆盖

### 分析

cluster sort 的性能收益来自 pread 时内核 readahead 的效率——相似向量集中在连续物理页面上。当中间实验（vecblock-cluster-reorder R1 full-cluster-reorder）对 NVMe LBA 空间造成碎片化后：

1. 原始 vecblocks 文件内容不变（md5 一致）
2. cluster-sorted 文件内容也不变（md5 一致）
3. 但 NVMe SSD 的物理页映射已碎片化
4. pread readahead 命中率下降
5. cluster sort 的 I/O 局部性优势消失

### 证据

| 场景 | 无 cluster | 碎片化 cluster sort | 重生成 cluster sort | Δ (重生成 vs 碎片化) |
|------|:---:|:---:|:---:|:---:|
| 256MB 1T | 1,474 | 1,512 (+2.6%) | 1,747 (+18.5%) | +15.5% |
| 256MB 16T | 3,340 | 3,636 (+8.9%) | 5,218 (+56.2%) | +43.5% |
| 512MB 1T | 1,925 | 1,952 (+1.4%) | 2,154 (+11.9%) | +10.3% |
| 512MB 16T | 6,308 | 6,970 (+10.5%) | 8,698 (+37.9%) | +24.8% |

"碎片化 cluster sort" 和 "重生成 cluster sort" 的输入文件 md5 相同，唯一区别是 NVMe 物理布局。

## 决策

1. 金标 pipeline (`run_sustained.sh`) 在 Config C 测量前自动重新生成 cluster-sorted 文件
2. 5 分钟内的重复调用跳过（避免 12 runs × 2min = 24min 额外开销）
3. BEH-037 条款补充可复现性要求

## 教训

- **md5 不是性能可复现性的充分条件**——NVMe 物理布局对 I/O 密集型 workload 有显著影响
- 金标 pipeline 必须从源头重新生成依赖物理布局的文件
- 任何涉及大量文件 I/O 的中间实验都可能碎片化 NVMe 空间

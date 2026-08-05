# Proposal: R5 - WILLNEED 下 REFINE_EF 重扫 + PQ 联合 {#PROP-REFINE-EF-R5}

> track: poc  
> Status: Pending  
> 日期: 2026-08-04  
> Role: amend  
> Parent: `spec/open/proposal-refine-ef.md` (Implemented)  
> 主题装订器: `poc/refine-ef-tuning/ndf/TOPIC.md`（[[BEH-025]]）  
> 关联: [[BEH-024]](stable), [[CON-SLA-014]], [[DEC-070]], [[CHR-006]]

## 1. 动机

R0-R4 基线是 pre-WILLNEED 时代（flat_vec=128MB，无 WILLNEED）。Trunk 已 promote WILLNEED（DEC-070），fine rerank 的 I/O 模式变了：

- 旧：pread 串行阻塞，majfault 是瓶颈
- 新：WILLNEED 异步 readahead，pread 变内存拷贝

需要验证：
1. WILLNEED 下 REFINE_EF 的 QPS 曲线是否变化
2. Recall≥95% 约束下是否有新空间（如 EF=250, EF=280）
3. 与 PQ M=24 联合：M=24+EF=X 能否同时满足 Recall≥95% 和更高 QPS

## 2. 实验设计

### 基线

Trunk 当前配置（WILLNEED=1, flat_vec=64MB, REFINE_EF=300, M=32）：
- DEEP10M 2GB: QPS=563, Recall=95.05%（io-pipelining correction 实测）

### 实验矩阵

| 轮次 | REFINE_EF | PQ M | L4_WILLNEED | 说明 |
|------|-----------|------|-------------|------|
| R5-base | 300 | 32 | 1 | 基线（Trunk 默认） |
| R5a | 250 | 32 | 1 | 精细扫描：95% 附近 |
| R5b | 200 | 32 | 1 | R1 复现（WILLNEED 下） |
| R5c | 250 | 24 | 1 | PQ 联合：M=24 精度更高? |
| R5d | 300 | 24 | 1 | PQ 联合基线 |
| R5e | 200 | 24 | 1 | PQ 联合极限 |

### 协议

- 数据集：DEEP10M
- cgroup：2GB（CON-SLA-014）
- sudo drop_caches + sudo cgroup
- 线程：1T
- queries：200
- 采集：QPS/Recall/RSS/refault/majfault

### 成功标准（探索）

| 指标 | 目标 |
|------|------|
| Recall | ≥95%（CHR-006 must） |
| QPS | > 563（基线提升） |
| RSS | ≤1700MB（2GB cgroup 内） |

如果 M=24+EF=250 能达到 Recall≥95%，则 QPS 可能有显著提升（M=24 的 PQ 计算更快 + EF=250 的候选更少）。

## 3. NDF 变更

- 本提案为 poc track amendment，不改 stable 条款
- 如有正结果（Recall≥95% + QPS 提升）→ 另开 promote 提案
- 如 M=24 无法达到 95% → 记录为 PQ 质量上限约束

## 4. 非目标

- 不改 Trunk `src/`
- 不改 BEH-024 stable
- 不改 REFINE_EF 默认值
- 不改 SLA 数字（Recall≥95% is must）

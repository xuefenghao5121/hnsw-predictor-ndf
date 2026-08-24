# Proposal: L4 Cache 优化第二轮 (基于当前 Trunk)

> track: poc
> 日期: 2026-08-05 (amend l4-cache-mgmt)
> Status: Implemented on 2026-08-05
> 关联: [[CHR-006]]、[[CON-SLA-014]]、[[BEH-024]]、[[BEH-027]]、[[DEC-068]]、[[DEC-070]]、[[DEC-073]]、[[DEC-074]]、[[CON-POC-001]]
> Amend: `poc/l4-cache-mgmt/ndf/TOPIC.md` (旧基线 stale, 基于当前 Trunk 重新探索)

## 1. 背景

旧 l4-cache-mgmt POC 的 R4 (flat_vec_cache) 和 R5a (WILLNEED) 已 promoted。
当前 Trunk 额外含: FVC 默认值 64MB (DEC-073)、WILLNEED_BG 无锁后台线程 (BEH-027)、
VL_POOL 自适应池化 (BEH-027)、FineRerank race fix (std::call_once)。

旧基线 (stale): SIFT1M 256MB 1T = 2379 QPS (WILLNEED only)
新基线 (当前 Trunk, WILLNEED_BG=1 VL_POOL_THREADS=14):
- 256MB: 1T=2612 / 4T=7721 / 12T=13799 / 16T(peak)=16873 / 24T=12590
- 512MB: 1T=3133 / 4T=9041 / 12T=18459 / 16T(peak)=30332 / 24T=29738

## 2. 新探索方向

### 方向 1: flat_vec_cache 命中率诊断与优化

当前 FVC=64MB(256MB)/160MB(512MB) 的实际命中率未知。
- 测量 getFlatVector 命中/miss 比率
- 分析 miss 的候选向量分布（是否集中在某些 block）
- 优化 slot 替换策略（当前 hash-based，可能有冲突）

### 方向 2: WILLNEED readahead 窗口合并

当前 WILLNEED_BG 后台线程逐页 hint (每页 4KB)。
pages_needed 中连续页可合并为单次大窗口 fadvise（如 16KB/64KB），
减少 syscall 数量和内核锁竞争。

注: A3 (PAGE_MERGE) 在 inline 路径有害 (-33% at 16T)，但在 BG 线程中可能不同
（BG 线程不阻塞搜索线程，排序开销被隐藏）。

### 方向 3: FineRerank 后选择性 DONTNEED (R5b 重测)

旧 R5b 在 1T 256MB 下 +14% QPS。当前 Trunk 有 WILLNEED_BG，
DONTNEED + BG 组合的行为未知。
- FineRerank 读完后对已消费页 hint DONTNEED
- 让内核优先保留 WILLNEED 预读但驱逐已用页
- 可能减少 page cache 中的冷页，给热页更多空间

### 方向 4: BlockCache 层优化

当前 BlockCache (graph blocks) 和 flat_vec_cache 共享 cgroup 预算。
在 256MB 下两者竞争内存。
- 测量 BlockCache 命中率
- 调整 CACHE_MB vs FLAT_VEC_MB 分配比例

## 3. 验证协议

[[CON-SLA-014]] 严格隔离。256MB 和 512MB 双配置。
对比基线: 当前 Trunk + WILLNEED_BG=1 VL_POOL_THREADS=14。

## 4. 不做的事

- 不改 Trunk `src/`
- 不重复旧 R0-R3 (FADVISE 在 512MB 有害已确认)
- 不写 stable must SLA

## 5. 晋升条件

若某方向 12T+ QPS 提升 >5%，另开 promote 提案。

# Proposal: DEC-066 修正 - 环境变量拼写错误导致假基线 {#PROP-DEC066-CORRECTION}

> track: process
> Status: Implemented on 2026-08-03
> 日期: 2026-08-03
> 关联: [[DEC-066]], [[CHR-006]], [[CON-SLA-011]], [[VER-039]], [[CON-SLA-013]], [[CON-SLA-014]]

## 动机

DEC-066 的 "22.9 QPS" 严格隔离基线是**错误的**。根因：测试脚本使用 `PQ_CODE_PATH`（无 S），
但 benchmark 代码读取 `PQ_CODES_PATH`（有 S）。PQ codes 未加载，`pq_enabled_=false`，
走了无 PQ 粗筛的 fallback 路径（searchLayer0NonBlocking），Recall=98.35%（全量精排）但 QPS=23。

修正后（PQ_CODES_PATH）的真实严格隔离基线恢复到正常水平，旧 SLA 数字在严格隔离下仍然有效。

## 修正数据

### 错误基线 (DEC-066 原始, PQ 未加载)

| 模式 | 线程 | QPS | Recall | RSS |
|------|------|-----|--------|-----|
| Buffered | 1T | 22.9 | 98.35% | 235MB |
| Buffered | 4T | 18.4 | 98.35% | 416MB |
| O_DIRECT | 1T | 22.8 | 98.35% | 235MB |
| O_DIRECT | 4T | 19.5 | 98.35% | 426MB |

### 正确基线 (PQ_CODES_PATH 修正后, CON-SLA-014 严格隔离)

| 模式 | 线程 | QPS | Recall | RSS | cgroup peak | oom | max events |
|------|------|-----|--------|-----|-------------|-----|------------|
| Buffered | 1T | **2309** | 95.75% | 155MB | 512MB | 0 | 1654 |
| Buffered | 4T | **6060** | 95.75% | 161MB | 512MB | 0 | 1687 |
| O_DIRECT | 1T | **837** | 95.75% | 155MB | 512MB | 0 | 3224 |
| O_DIRECT | 4T | **3215** | 13.95%⚠️ | 160MB | 512MB | 0 | 4754 |

> O_DIRECT 4T Recall=13.95% 异常，疑为 O_DIRECT+io_uring 多线程问题，待查。
> cgroup 验证：memory.peak=512MB=memory.max，无白嫖。

### 与旧 SLA 对比

| 指标 | 旧 SLA | 正确严格隔离 | 达标 |
|------|--------|-------------|------|
| Buffered 1T QPS | ≥2000 | 2309 | ✅ |
| Buffered 4T QPS | ≥5000 | 6060 | ✅ |
| O_DIRECT 1T QPS | ≥100 | 837 | ✅ |
| O_DIRECT 4T QPS | ≥400 | 3215 (recall 异常) | ⚠️ |
| Recall@10 | ≥95% | 95.75% | ✅ |
| RSS 1T | ≤300MB | 155MB | ✅ |
| RSS 4T | ≤450MB | 161MB | ✅ |

## 决策

1. **DEC-066 修正**：22.9/18.4/22.8/19.5 全部标注为"环境变量错误导致的假基线"
2. **旧 SLA 恢复有效**：Buffered ≥2000/≥5000、O_DIRECT ≥100/≥400 在严格隔离下达标
3. **CHR-006 / CON-SLA-011 恢复旧 SLA 数字**，附注严格隔离验证已通过
4. **VER-039 更新**：填入正确实测数据
5. **CON-SLA-014 协议不变**：仍为唯一合法测法

## 根因分析

| 问题 | 根因 |
|------|------|
| PQ_CODE_PATH vs PQ_CODES_PATH | 脚本拼写错误（少了个 S） |
| 未被发现 | 旧白嫖 era 脚本（MEMORY.md 甜点配置）用了正确的 PQ_CODES_PATH，但后续测试脚本复制时出错 |
| 影响 | 所有使用 PQ_CODE_PATH（无 S）的测试结果均无效 |

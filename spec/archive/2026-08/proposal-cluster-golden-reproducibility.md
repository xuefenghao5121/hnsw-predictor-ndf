# Proposal: Cluster-Sorted Vecblocks 金标可复现性保障

> track: process
> status: implemented
> implemented: 2026-08-11
> created: 2026-08-11
> scope: 金标 pipeline + BEH-037 + cfg-m24-ef60 + run_golden.sh

## 问题

### 现象

BEH-037 cluster sort (k=1024) 在 POC R2 中报告 +23.4% @1T / +50.8% @16T。
金标重跑（3 轮 mean）只测出 +2.6% / +8.9%，差距 15-40pp。
重新做 k-means 生成新文件后，金标恢复到 +18.5% / +56.2%（与 POC R2 一致）。

### 根因

1. **NVMe 物理布局依赖**：within-block cluster sort 的性能收益来自 pread 时内核
   readahead 的效率——相似向量在连续物理页面上。当中间实验（如 R1 full-cluster-reorder）
   对 NVMe LBA 空间造成碎片化后，即使文件内容不变（md5 一致），物理页映射不再连续，
   cluster sort 的 I/O 局部性优势消失。

2. **金标脚本不可复现**：`run_golden.sh` 假定 cluster-sorted vecblocks 文件已存在且有效，
   不重新生成。如果文件因中间实验碎片化，金标数字会系统性偏低，但无人能发现。

3. **配置缺少版本追踪**：`cfg-m24-ef60.md` 的 `vecblocks_path` 只指向一个文件路径，
   不记录该文件是何时、从哪个输入 vecblocks 生成的。无法判断是否需要重新生成。

### 影响

- 金标基线数字不可信（可能基于碎片化文件）
- 回归检测失效（性能退化被归因为"运行变异"）
- BEH-037 条款的效果声明无法在金标中复现

## 修改计划

### 1. `run_golden.sh`: 自动重新生成 cluster-sorted vecblocks

在 Config C 的金标运行前，自动执行 `cluster_reorder` 重新生成 cluster-sorted 文件：

```bash
# 在 run_golden.sh 中，cfg-m24-ef60 的场景开始前：
if [[ "$CFG" == "cfg-m24-ef60" ]]; then
  CLUSTER_K=1024
  SRC_VB="${DATA_PREFIX}_vecblocks_64k.bin"
  CLUSTER_VB="${DATA_PREFIX}_vecblocks_64k_cluster${CLUSTER_K}.bin"
  echo "[Golden] Regenerating cluster-sorted vecblocks (k=$CLUSTER_K)..."
  make -s build/cluster_reorder
  build/cluster_reorder 128 "$SRC_VB" "$CLUSTER_VB" "$CLUSTER_K"
fi
```

**保证**：每次金标测量前，cluster-sorted 文件都是新写入的连续物理布局。

### 2. `cfg-m24-ef60.md`: 增加 cluster 生成参数

```markdown
> cluster_sort: BEH-037 (k=1024)
> cluster_k: 1024
> cluster_input: output/sift1m_m24/sift1m_m24_vecblocks_64k.bin
> vecblocks_path: output/sift1m_m24/sift1m_m24_vecblocks_64k_cluster1024.bin
```

`run_sustained.sh` 解析 `cluster_k` + `cluster_input`，若文件不存在或需要重新生成，
自动调用 `cluster_reorder`。

### 3. BEH-037 条款: 补充可复现性注意事项

在 `spec/20-behavior/cluster-vecblock-layout.md` 增加：

```markdown
## 可复现性要求

> ⚠️ cluster-sorted vecblocks 的 I/O 局部性收益依赖 NVMe 物理页连续性。

- 金标测量前 MUST 重新执行 `cluster_reorder` 生成新文件
- 禁止复用中间实验（如 full-cluster-reorder）触碰过的 vecblocks 文件做 cluster sort 输入
- 若 md5 一致但性能退化 >10%，应怀疑物理布局碎片化
```

### 4. `run_sustained.sh`: 增加 cluster 自动生成逻辑

从 config 解析 `cluster_k` 和 `cluster_input`，若存在则自动 `cluster_reorder`：

```bash
# 解析 cluster 参数
CONFIG_CLUSTER_K=$(grep '^> *cluster_k:' "$CONFIG_FILE" | head -1 | sed 's/.*cluster_k: *//')
CONFIG_CLUSTER_INPUT=$(grep '^> *cluster_input:' "$CONFIG_FILE" | head -1 | sed 's/.*cluster_input: *//')

# 若声明了 cluster_k 且对应的 vecblocks_path 存在，自动重新生成
if [[ -n "$CONFIG_CLUSTER_K" && -n "$CONFIG_CLUSTER_INPUT" ]]; then
  echo "[Cluster] Regenerating k=$CONFIG_CLUSTER_K from $CONFIG_CLUSTER_INPUT..."
  build/cluster_reorder 128 "$CONFIG_CLUSTER_INPUT" "$CONFIG_VECBLOCKS_PATH" "$CONFIG_CLUSTER_K"
fi
```

### 5. DEC: 记录物理布局依赖发现

新增 `spec/decisions/dec-cluster-physical-layout.md` 记录：
- 发现：md5 相同的 vecblocks 文件因物理碎片化导致 15%+ 性能差异
- 根因：NVMe LBA 碎片化影响 pread readahead 效率
- 措施：金标 pipeline 强制重新生成 cluster-sorted 文件

## 涉及条款

| 文件 | 变更类型 |
|------|---------|
| `scripts/run_golden.sh` | 新增 cluster 重生成步骤 |
| `scripts/run_sustained.sh` | 新增 cluster 自动生成逻辑 |
| `spec/50-verification/configs/cfg-m24-ef60.md` | 新增 cluster_k / cluster_input 字段 |
| `spec/20-behavior/cluster-vecblock-layout.md` | 新增可复现性要求段落 |
| `spec/decisions/dec-cluster-physical-layout.md` | 新增 DEC |

## 验证

1. `run_golden.sh --config cfg-m24-ef60` 自动重生成 cluster 文件后跑 4 场景
2. 金标数字与 POC R2 一致（±5%）
3. graphcheck 0 errors

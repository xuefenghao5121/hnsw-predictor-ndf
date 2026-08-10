# Proposal: run_sustained.sh 金标测试标准绑定 + 配置输入支持

> track: promote
> status: implemented on 2026-08-10
> date: 2026-08-10
> affects: API-016, API-019, CON-SLA-020, CON-GOLDEN-001
<!-- ndf: refines=API-019,CON-SLA-020,CON-GOLDEN-001 depends-on=API-016,CON-SLA-014 -->

## 背景

当前测试脚本格局：

| 脚本 | 定位 | 问题 |
|------|------|------|
| `scripts/run_sustained.sh` | CON-SLA-020 sustained runner | 参数硬编码 M=16 默认路径；Config B/C 需手动 env 覆盖 |
| `scripts/run_golden.sh` | CON-GOLDEN-001 自动化 | 硬编码 M=16；只跑 Config A；3 轮 |
| `scripts/cgroup_utils.sh` | API-016 工具库 | ✅ 稳定 |

`run_sustained.sh` 已有 env 覆盖（BIN, DATA_PREFIX, EF），但：
1. **没有 config_id 输入**：用户必须知道 M=24 对应 `output/sift1m_m24/` + EF=60
2. **金标配置文件（`spec/50-verification/configs/`）与脚本脱钩**：配置在 spec 中定义，但脚本不读取
3. **run_golden.sh 只跑 Config A**：金标基线已有三组配置，但自动化只覆盖一组

## 变更内容

### 1. run_sustained.sh 添加 `--config <config_id>` 输入

支持从 `spec/50-verification/configs/<config_id>.md` 读取配置参数。

```bash
# 用法示例：
# Config A (默认，向后兼容)
CGROUP_MB=256 THREADS=1 bash scripts/run_sustained.sh

# Config C (M=24 EF=60)
bash scripts/run_sustained.sh --config cfg-m24-ef60

# Config C + 自定义 cgroup/线程
CGROUP_MB=256 THREADS=1 bash scripts/run_sustained.sh --config cfg-m24-ef60
```

`--config` 解析逻辑：从 config 文件的 `data_path:` 和参数表读取 DATA_PREFIX、EF 等。
未指定 `--config` 时，默认行为不变（Config A, M=16, EF=100）。

### 2. run_sustained.sh 绑定金标基线

输出中标注当前使用的 config_id 和对照的 baseline_id：

```
=== ver043 | cfg-m24-ef60 | bl-trunk-golden-434c6f5 | 256MB | 1T | N=1000 | R=15 | seed=42 ===
```

### 3. run_golden.sh 扩展为三配置

从只跑 Config A 扩展为跑 CON-GOLDEN-001 全部三组（A/B/C）。

### 4. 条款更新

- **API-019**（CLI）：添加 `--config` 参数说明
- **CON-SLA-020**：绑定 `scripts/run_sustained.sh` 为权威测试载体
- **CON-GOLDEN-001**：绑定 `scripts/run_golden.sh` 为金标自动化载体

## 不改的项

- `scripts/cgroup_utils.sh`（API-016 工具库，已稳定）
- benchmark CLI 二进制接口（`benchmark_sustained` 参数不变）
- Trunk `src/`、`include/`、`tests/`

## 向后兼容

- 不传 `--config` → 默认 Config A（M=16, EF=100, `output/sift1m/`）
- 已有 env 覆盖（BIN, DATA_PREFIX, EF）保留，优先级高于 `--config`
- `run_golden.sh` 不带参数 → 跑全部三组（原行为为只跑 Config A，变更后会跑三组）

## 验证

- `bash -n scripts/run_sustained.sh`（语法检查）
- `bash scripts/run_sustained.sh --config cfg-m24-ef60 --dry-run`（dry-run 模式，打印参数不执行）
- graphcheck: 0 hard errors

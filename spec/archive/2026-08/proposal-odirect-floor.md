# Proposal: O_DIRECT 地板图一致性修补 {#PROP-ODIRECT-FLOOR}

> Status: Implemented on 2026-07-31
> 场景: 场景3（规范重构 / 审核闭环）
> 日期: 2026-07-31
> 关联: [[DEC-059]], [[DEC-060]]；审核意见（双重真相 / L0 越界 / 缺提案）

## 动机

DEC-059/060 与 Charter/CON 的战略重定位方向正确，但图未闭合：多处仍写
「FINE_DIRECT=诊断 / page cache 免费 / verifies=DEC-030」，且 `CHR-006`(L0)
混入优化机制与 250–300 目标 QPS，易被当成 must SLA。

## 变更清单（已落地）

1. **死链 / 旧叙事同步**
   - `DEF-014`：FINE_DIRECT = 性能地板 / 优化基座（DEC-059），非诊断
   - `DEC-039`：定位改挂 DEC-059
   - `DEC-057`：§2/§3 标注由 DEC-059 修正（核心价值补充；page cache 非免费）
   - `VER-030`：`verifies=` → DEC-059；去掉「诊断模式」措辞
   - `p4-decisions.md` 文件头：关联改为 DEC-059
2. **`CON-HONEST-002`**：`refines=` 去掉已 superseded 的 `DEC-030`，改为
   `refines=DEC-039,DEC-059`（`depends-on=DEC-057` 可保留在 SLA 侧）
3. **`CHR-006` 收薄**：L0 只保留双轨 MUST 数字 + 一句 SoT；Layer1/2 细节与
   250–300 / 四方向仅存于 DEC-059/060；`CHR-004` P3 只引用决策、不列机制
4. **`CHR-001`**：补一句 cgroup anon+file 与 O_DIRECT 地板意图（对齐 DEC-059 affects）
5. **本提案**：补齐流程缺口（先提案后固定目录）

## 非本轮

- 不为 DEC-060 四方向新建 BEH/VER（仍属 roadmap ADR，待增量特性提案）
- 不抬高 `CON-SLA-011` 阈值

## 验收

- [x] 固定目录无「FINE_DIRECT=诊断」活叙事（历史 superseded 正文除外）
- [x] `CON-HONEST-002` 不 `refines` DEC-030
- [x] `CHR-006` 无 250–300 目标数字、无四方向机制列表
- [x] `VER-030` 验证 DEC-059

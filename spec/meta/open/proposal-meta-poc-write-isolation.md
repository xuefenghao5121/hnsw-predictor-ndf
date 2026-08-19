# Proposal: POC 写入隔离（方案 A） {#PROP-META-POC-WRITE-ISOLATION}

> track: process  
> Status: Implemented on 2026-08-08  
> 日期: 2026-08-08  
> 关联: [[BEH-018]], [[ARCH-008]], [[CHR-008]]  
> 场景: 双轨 / 写入边界  
> 原则: 写入隔离 + 改则必拷；允许只读链未改 Trunk；Harness / state.json 不动

## 1. 动机

探索期易直接改 Trunk `include/` 头文件，破坏 POC 写入面独立。[[BEH-018]] 第 6 条
此前未点名 `include/` / `tests/`。

## 2. 决策（方案 A）

1. [[BEH-018]]：poc MUST NOT 修改 Trunk `src/**`、`include/**`、`tests/**`；要改的
   `.h`/`.cpp` MUST 先复制进 `poc/<topic>/`；MAY 只读链未改动的 Trunk 源/头。
2. [[ARCH-008]]：探索可执行改动含头文件，不得以「只改 include」绕过 `poc/`。
3. AGENTS / CLAUDE / poc README 薄同步。
4. 工具：`ndf_poc_isolation.py` 检测 topic 相关 commit / 工作区是否触及禁写路径。

## 3. 非范围

不批量改造存量 POC Makefile；不要求整树 vendor（方案 B）。

## 4. 验收

条款 + 文档落地；`graphcheck --meta` hard_errors=0；隔离脚本可检出禁写路径。

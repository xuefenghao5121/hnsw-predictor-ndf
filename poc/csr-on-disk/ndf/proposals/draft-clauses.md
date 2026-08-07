# Draft Clauses: csr-on-disk

## L0 CSR 邻接表磁盘驻留 {#BEH-036}
<!-- ndf: kind=req level=tbd layer=L1 status=draft since=0.9.12 source=proposed -->
<!-- ndf: topic=csr-on-disk -->

当 `CSR_FILE_PATH` 指定 CSR compact 文件时，L0 CSR 压缩邻接表 MAY 存储在磁盘文件中，
搜索时通过 mmap + page cache 按需读取。`adj_csr_byte_offsets_` MUST 保留在内存中
（节点级随机访问索引）。

启用时：
- CSR compact 数据 MUST NOT 加载到进程内存（`adj_csr_compact_` 为空）
- 搜索 MUST 通过 mmap 映射的文件区域读取 CSR 字节流
- `decodeCsrNeighbors()` MUST 从 mmap 指针解码，行为与内存路径一致
- recall MUST ≥ 95%（CSR 内容不变，仅存储位置改变）

> rationale: CSR compact 在 SIFT1M 占 init RSS 30%（47MB），100M 规模达 4.7GB。
> BFS 重排使图相邻节点在文件中物理相邻，4KB page 可容纳 ~83 个 CSR entries，
> 为 page cache 提供天然局部性。[[DEC-010]] 已预判"100M CSR 上磁盘是更有效方案"。

## CSR 磁盘文件接口 {#API-020}
<!-- ndf: kind=interface level=tbd layer=L1 status=draft since=0.9.12 source=proposed -->
<!-- ndf: topic=csr-on-disk refines=API-002 -->

`CSR_FILE_PATH` 环境变量指定 CSR compact 独立文件路径。

文件格式：纯压缩字节流（`adj_csr_compact_` 的原始内容），无 header。
节点 i 的 CSR 数据位于 `[byte_offsets_[i], byte_offsets_[i+1])` 字节范围。

当 `CSR_FILE_PATH` 未设置时，使用原有内存加载路径（从 graph_structure.bin 加载）。

| 参数 | 默认 | 说明 |
|------|------|------|
| `CSR_FILE_PATH` | (空) | CSR compact 文件路径；空=内存加载（原有行为） |

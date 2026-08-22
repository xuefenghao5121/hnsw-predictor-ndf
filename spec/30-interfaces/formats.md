# Interfaces — 二进制文件格式

> 条款索引: `API-004`

## 二进制文件格式 {#API-004}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

### Graph Structure (MAGIC_GRAPH = 0x47524148)

```
Offset  Size   Field
0       4      magic (0x47524148 "HARG")
4       4      version (1 or 2 for compressed)
8       4      num_nodes
12      4      dim
16      4      maxM
20      4      maxM0
24      4      entry_point
28      4      max_level (int32)
32      4      data_size
36      4      reserved
40      4      padding
44      N*4    levels[N]
44+N*4  N*dim*4 vectors[N*dim]
...     N*8    labels[N]
...     var    L0 adjacency lists (cnt:u16 + cnt*u32 per node)
...     var    upper adjacency lists
```

### Blocks (MAGIC_BLOCKS = 0x424C4B48)

```
Offset   Size   Field
0        4      magic (0x424C4B48 "HKLB")
4        4      version
8        4      block_size (64KB or 256KB)
12       4      num_blocks
16..4095 pad    (BLOCKS_FILE_HEADER_SIZE = 4096)
4096     block_size  Block[0]
4096+BS  block_size  Block[1]
...

Per Block (标准 BlockHeader, 24B):
  0        4      block_id
  4        4      node_count
  8        4      data_offset
  12       4      adj_offset
  16       1      flags (bit0: delta_varint；bit1 在标准头中不作为 VecOnly 判定依据)
  17       7      reserved_pad
  24       var    node_ids[count]
  data_off var    vectors[count*dim]
  adj_off  var    adjacency lists

Per Block (VecOnlyHeader, 16B) — `write_blocks_veconly` / Fine Rerank 向量块:
  0        4      block_id
  4        4      node_count
  8        4      data_offset
  12       4      flags (u32；bit1 = FLAG_VEC_ONLY=0x02 MUST 置位)
  16       var    node_ids + vectors（无邻接表）

> L1 澄清（原 CONFLICT-001）: VecOnly 与标准 Block **不是**同一 header。
> 判定 MUST 先按 VecOnlyHeader 在 offset 12 读 `flags:u32` 检测 `FLAG_VEC_ONLY`；
> 未置位时再按标准 BlockHeader 解析。禁止仅依赖标准头 offset 16 的 `flags:u8`
> 或把标准头 `adj_offset` 低位误当作 VecOnly 标志（见 [[BEH-009]]）。
```

### Route Table (MAGIC_ROUTE = 0x524F5554)

```
Offset   Size   Field
0        4      magic (0x524F5554 "ROUT")
4        4      num_entries (= num_nodes)
8        4      block_size
12       4      reserved
16       N*4    route[N] (node_id → block_id, uint32)
```

### BFS Order (MAGIC_BFS = 0x42465300)

```
Offset   Size   Field
0        4      magic (0x42465300 "BFS\0")
4        4      num_nodes
8        4      entry_point
12       4      reserved
16       N*4    old_to_new[N]
16+N*4   N*4    new_to_old[N]
```

### PQ Codes (magic "PQCO")

```
Offset   Size   Field
0        4      magic "PQCO"
4        8      n (uint64)
12       4      M (uint32)
16       4      nbits (uint32)
20       4      dim (uint32)
24       4      codebook_M (uint32)
28       4      codebook_K (uint32)
32       4      codebook_dsub (uint32)
36       M*K*dsub*4 codebook floats
...      n*M     pq_codes bytes (old_id order)
```

### Ground Truth (GT)

```
Offset   Size   Field
0        4      n_queries (uint32)
4        4      K (uint32)
8        n*K*8  neighbor_ids (uint64, only ids, no distances)
```

### FVECS

```
Per record: dim(int32) + dim * float32
```


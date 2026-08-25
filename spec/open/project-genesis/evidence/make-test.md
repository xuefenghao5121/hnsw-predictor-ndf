# Evidence — make test（VER-007）

> hop: genesis_design（continue_baseline）
> date: 2026-08-25
> trunk_sha: d0ae5dd4bdd44af73498f98ea1ac0b86cee0f755
> clause: [[VER-007]]

## 1. `make test`（构建）

```
$ make test
make: Nothing to be done for 'test'.
```

- 3 个测试二进制均已在 `build/` 就绪（`test_block_cache`、`test_disk_hnsw`、
  `test_pq_search_quality`），构建通过（exit 0）。

## 2. `test_disk_hnsw`（SIFT1M，200q，cached 模式）

```
$ ./build/test_disk_hnsw output/sift1m_index.bin output/sift1m_graph.bin \
    output/sift1m_bfs.bin output/sift1m_blocks_64k.bin output/sift1m_route_64k.bin \
    data/sift_base.fvecs data/sift1m_query200.fvecs 10 50 64 \
    --io-mode=cached --layout=bfs --policy=lru
```

- Full-memory HNSW recall@k vs GT: 95.3%
- DiskHNSW recall@k vs GT: 95.2%
- DiskHNSW recall@k vs HNSW: 100.0%
- **Verdict: DiskHNSW vs HNSW recall >= 95%: PASS ✅**（exit 0）

## 3. 未运行项（fixture / 数据缺失）

| 测试 | 状态 | 原因 |
|------|------|------|
| `test_block_cache` | 未运行 | 需合成 fixture（`test_graph.bin`/`test_blocks.bin`/`test_route.bin`/`test_bfs.bin`），仓库未携带生成器 |
| `test_pq_search_quality` | 未运行 | 硬编码 `data/deep10m_test.fvecs` / `output/deep10m_pq_*` 路径，本仓库未提供 DEEP10M PQ 数据 |

## 结论

`make test` 构建通过；可运行的核心正确性测试 `test_disk_hnsw` PASS（recall 95.2% vs
GT、100% vs HNSW）。两个单元测试因 fixture/data 缺失未运行，属 `VER-007`（SHOULD）的
证据缺口，不影响骨架晋升。

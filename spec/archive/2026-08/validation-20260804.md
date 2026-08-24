# 验证报告: WILLNEED promote 编译验证 (场景5)

> 日期: 2026-08-04  
> 提案: `spec/archive/2026-08/proposal-promote-willneed.md`  
> 变更: `src/core/disk_hnsw.cpp` +8 lines (L4_WILLNEED fadvise loop)  
> 条款: BEH-024, API-012, DEC-070

## 编译

```
make -C /home/huawei/hnsw-predictor-ndf
```

结果: **通过** ✅

- `build/benchmark_diskhnsw` 生成成功
- 无 error，仅 pre-existing warnings（unused parameter, posix_memalign return value 等）
- 代码位置: `src/core/disk_hnsw.cpp:1754-1761`（pages_needed 填充后, kFinePread 分支前）

## 代码审查

```cpp
// L4 WILLNEED: hint kernel to prefetch fine rerank pages (BEH-024, DEC-070)
static const bool kL4Willneed = std::getenv("L4_WILLNEED") && std::atoi(std::getenv("L4_WILLNEED")) != 0;
if (kL4Willneed && !pages_needed.empty() && vec_blocks_fd_ >= 0) {
    for (uint32_t pg : pages_needed) {
        posix_fadvise(vec_blocks_fd_, (off_t)pg << 12, 4096, POSIX_FADV_WILLNEED);
    }
}
```

- `static const bool` 确保环境变量只读一次
- `vec_blocks_fd_ >= 0` 防御性检查
- 默认关闭（`L4_WILLNEED=0`），不影响现有行为
- 插入位置在 pread/io_uring 分支前，两条路径都受益

> source: poc/l4-cache-mgmt/ndf/TOPIC.md ; proposals/proposal-l4-r5-willneed-selective.md ; COMMITS.md @ 2f008f7
> track: promote ; Topic: l4-cache-mgmt

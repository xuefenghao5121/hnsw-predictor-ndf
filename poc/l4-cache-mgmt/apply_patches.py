#!/usr/bin/env python3
"""Apply L4 cache management patches to create POC copies."""
import shutil
import os
import sys

SRC_DIR = "../../src/core"
INCLUDE_DIR = "../../include"
BENCH_DIR = "../../src/benchmark"
OUT_DIR = "."

patches_applied = []

def copy_and_patch(src, dst, patches):
    """Copy file and apply string replacements."""
    with open(src, 'r') as f:
        content = f.read()
    for old, new, desc in patches:
        if old not in content:
            print(f"WARNING: patch target not found: {desc}")
            continue
        content = content.replace(old, new, 1)
        patches_applied.append(desc)
    with open(dst, 'w') as f:
        f.write(content)
    print(f"  patched {dst} ({len(patches)} patches)")

# ---- Patch disk_hnsw.cpp ----
disk_patches = [
    # After BFS loading + CSR building, evict graph/BFS file page cache
    (
    """    std::cout << "[DiskHNSW] BlockCache (pluggable) initialized" << std::endl;
    cache_slots_ = cache_->getCacheSlots();
}""",
    """    std::cout << "[DiskHNSW] BlockCache (pluggable) initialized" << std::endl;
    cache_slots_ = cache_->getCacheSlots();

    // L4 POC: Evict metadata file page cache after loading (L4_EVICT_META=1)
    // graph (587MB) + BFS (7.7MB) are no longer needed in page cache after CSR is built
    static const bool kL4EvictMeta = std::getenv("L4_EVICT_META") && std::atoi(std::getenv("L4_EVICT_META")) != 0;
    if (kL4EvictMeta) {
        size_t evicted = 0;
        // Evict graph file
        int gfd = open(graph_path.c_str(), O_RDONLY);
        if (gfd >= 0) {
            posix_fadvise(gfd, 0, 0, POSIX_FADV_DONTNEED);
            close(gfd);
            evicted += 587;  // approximate
        }
        // Evict BFS file
        int bfd = open(bfs_path.c_str(), O_RDONLY);
        if (bfd >= 0) {
            posix_fadvise(bfd, 0, 0, POSIX_FADV_DONTNEED);
            close(bfd);
            evicted += 8;
        }
        std::cerr << "[L4] Evicted metadata page cache (~" << evicted << "MB): graph+bfs" << std::endl;
    }
}""",
    "Add L4_EVICT_META: evict graph+BFS page cache after init"
    ),
]

print("Patching disk_hnsw.cpp -> disk_hnsw_l4.cpp")
copy_and_patch(
    os.path.join(SRC_DIR, "disk_hnsw.cpp"),
    os.path.join(OUT_DIR, "disk_hnsw_l4.cpp"),
    disk_patches
)

# ---- Copy header unchanged ----
print("Copying disk_hnsw.h")
shutil.copy2(os.path.join(INCLUDE_DIR, "disk_hnsw.h"), os.path.join(OUT_DIR, "disk_hnsw_l4.h"))

# ---- Copy benchmark unchanged (just include different header) ----
print("Patching benchmark -> benchmark_l4.cpp")
with open(os.path.join(BENCH_DIR, "benchmark_diskhnsw.cpp"), 'r') as f:
    bench = f.read()
# No header change needed - disk_hnsw_l4.cpp exports same symbols
# Just copy as-is
with open(os.path.join(OUT_DIR, "benchmark_l4.cpp"), 'w') as f:
    f.write(bench)
print(f"  copied benchmark_l4.cpp")

# ---- Copy other source files needed for build ----
for f in ["block_cache.cpp"]:
    src = os.path.join(SRC_DIR, f)
    dst = os.path.join(OUT_DIR, f)
    if not os.path.exists(dst):
        shutil.copy2(src, dst)
        print(f"  copied {f}")

print(f"\nTotal patches applied: {len(patches_applied)}")
for p in patches_applied:
    print(f"  - {p}")

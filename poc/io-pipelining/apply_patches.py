#!/usr/bin/env python3
"""Apply I/O Pipelining patches to poc/io-pipelining/disk_hnsw_pipe.cpp"""
import sys

fpath = sys.argv[1]
with open(fpath, 'r') as f:
    c = f.read()

patches = []

# 1. Add <unordered_set> include
patches.append((
    '#include <unordered_map>\n',
    '#include <unordered_map>\n#include <unordered_set>\n'
))

# 2. Add thread_local pipe_ring_ definition
patches.append((
    'thread_local std::vector<uint32_t> DiskHNSW::csr_decode_buf_;\n',
    'thread_local std::vector<uint32_t> DiskHNSW::csr_decode_buf_;\n\n'
    '// I/O Pipelining: thread_local pipe_ring_ (BEH-021 draft)\n'
    'thread_local std::unique_ptr<IoUring> DiskHNSW::pipe_ring_;\n'
))

# 3. Add pipe_ring_ init in buildFineRerank
patches.append((
    '''    try {
        vec_ring_ = std::make_unique<IoUring>(256);
        vec_ring_->setBufferSize(8192);  // 8KB slots: 相邻页可合并为一次 8KB 读
    } catch (const std::exception& e) {
        std::cerr << "[FineRerank] io_uring init failed: " << e.what() << std::endl;
        close(fd);
        return false;
    }
    vec_blocks_fd_ = fd;''',
    '''    try {
        vec_ring_ = std::make_unique<IoUring>(256);
        vec_ring_->setBufferSize(8192);  // 8KB slots: 相邻页可合并为一次 8KB 读
    } catch (const std::exception& e) {
        std::cerr << "[FineRerank] io_uring init failed: " << e.what() << std::endl;
        close(fd);
        return false;
    }

    // I/O Pipelining: 初始化 pipe_ring_ (BEH-021 draft, PIPE_FINE=1)
    static const bool kPipeFineInit = std::getenv("PIPE_FINE") && std::atoi(std::getenv("PIPE_FINE")) != 0;
    if (kPipeFineInit) {
        try {
            pipe_ring_ = std::make_unique<IoUring>(kPipeRingEntries);
            pipe_ring_->setBufferSize(4096);
            pipe_ring_capacity_ = kPipeBufCount;
            std::cerr << "[PipeFine] pipe_ring_ initialized (entries=" << kPipeRingEntries
                      << ", buf=" << kPipeBufCount << "x4KB)" << std::endl;
        } catch (const std::exception& e) {
            std::cerr << "[PipeFine] pipe_ring_ init failed (pipelining disabled): " << e.what() << std::endl;
        }
    }

    vec_blocks_fd_ = fd;'''
))

# 4. Add pipe prefetch lambda at start of searchLayer0
old_lambda = '''DiskHNSW::searchLayer0(uint32_t entry_new_id, const float* query, size_t ef,
                       VisitedList& visited) {
    // 使用最大堆维护top candidates（距离大的在堆顶，方便淘汰）
    // 使用最小堆维护candidate set（距离小的在堆顶，优先展开）
    std::priority_queue<std::pair<float, uint32_t>,
                        std::vector<std::pair<float, uint32_t>>,
                        std::less<std::pair<float, uint32_t>>> top_candidates;  // 最大堆
    std::priority_queue<std::pair<float, uint32_t>,
                        std::vector<std::pair<float, uint32_t>>,
                        std::greater<std::pair<float, uint32_t>>> candidate_set;  // 最小堆'''

new_lambda = '''DiskHNSW::searchLayer0(uint32_t entry_new_id, const float* query, size_t ef,
                       VisitedList& visited) {
    // 使用最大堆维护top candidates（距离大的在堆顶，方便淘汰）
    // 使用最小堆维护candidate set（距离小的在堆顶，优先展开）
    std::priority_queue<std::pair<float, uint32_t>,
                        std::vector<std::pair<float, uint32_t>>,
                        std::less<std::pair<float, uint32_t>>> top_candidates;  // 最大堆
    std::priority_queue<std::pair<float, uint32_t>,
                        std::vector<std::pair<float, uint32_t>>,
                        std::greater<std::pair<float, uint32_t>>> candidate_set;  // 最小堆

    // ---- I/O Pipelining: Phase A 预取 (BEH-021 draft, PIPE_FINE=1) ----
    static const bool kPipeFine = std::getenv("PIPE_FINE") && std::atoi(std::getenv("PIPE_FINE")) != 0;
    static const int kPipeThreshold = []() {
        const char* e = std::getenv("PIPE_THRESHOLD");
        if (!e) return -1;
        return std::atoi(e);
    }();
    static const bool kPipeL4 = std::getenv("PIPE_L4") && std::atoi(std::getenv("PIPE_L4")) != 0;
    static const bool kFineDirectPipe = std::getenv("FINE_DIRECT") && std::atoi(std::getenv("FINE_DIRECT")) != 0;
    std::unordered_set<uint32_t> piped_pages;
    std::unordered_map<uint32_t, int> pipe_page_bufidx;
    int pipe_rank_counter = 0;
    int pipe_submit_counter = 0;
    int effective_threshold = (kPipeThreshold > 0) ? kPipeThreshold : (int)ef;

    auto tryPipePrefetch = [&](uint32_t nid) {
        if (!pipe_ring_ || !fine_rerank_ok_) return;
        if (nid >= graph_.num_nodes) return;
        uint32_t b = vec_route_table_[nid];
        uint64_t off = 4096ull + (uint64_t)b * vec_block_size_
                     + block_data_offset_[b]
                     + (uint64_t)node_slot_table_[nid] * dim_ * sizeof(float);
        uint32_t page0 = (uint32_t)(off >> 12);
        uint16_t oip = (uint16_t)(off & 4095);
        bool cross = (oip + dim_ * sizeof(float)) > 4096;
        if (piped_pages.count(page0)) return;
        int buf_idx = pipe_ring_->allocBuffer();
        if (buf_idx < 0) {
            if (kPipeL4 && !kFineDirectPipe && vec_blocks_fd_ >= 0) {
                readahead(vec_blocks_fd_, (off_t)page0 << 12, 4096);
            }
            return;
        }
        uint64_t ud = ((uint64_t)(buf_idx + 1) << 32) | page0;
        pipe_ring_->submitReadNF(vec_blocks_fd_, (off_t)page0 << 12, 4096, buf_idx, ud);
        piped_pages.insert(page0);
        pipe_page_bufidx[page0] = buf_idx;
        if (cross) {
            int buf2 = pipe_ring_->allocBuffer();
            if (buf2 >= 0) {
                uint64_t ud2 = ((uint64_t)(buf2 + 1) << 32) | (uint64_t)(page0 + 1);
                pipe_ring_->submitReadNF(vec_blocks_fd_, (off_t)(page0 + 1) << 12, 4096, buf2, ud2);
                piped_pages.insert(page0 + 1);
                pipe_page_bufidx[page0 + 1] = buf2;
            }
        }
        if (++pipe_submit_counter >= 8) {
            pipe_ring_->flushSqe();
            pipe_ring_->submit();
            pipe_submit_counter = 0;
        }
    };'''

patches.append((old_lambda, new_lambda))

# 5. Add pipe_ring_ flush before return in searchLayer0
patches.append((
    '    // 将top_candidates转换为最小堆返回',
    '    // I/O Pipelining: flush pipe_ring_ SQEs before returning (BEH-021 draft)\n'
    '    if (kPipeFine && pipe_ring_) {\n'
    '        pipe_ring_->flushSqe();\n'
    '        pipe_ring_->submit();\n'
    '    }\n\n'
    '    // 将top_candidates转换为最小堆返回'
))

# 6-9. Add tryPipePrefetch calls at 4 PQ emplace sites
# Site 1: cache-miss fallback PQ
patches.append((
    '''                        if (!top_candidates.empty()) lowerBound = top_candidates.top().first;
                    }
                } else if (cache_->isInCache(nblock)) {
                    const float* nvec = cache_->getNodeVector(nid);''',
    '''                        if (!top_candidates.empty()) lowerBound = top_candidates.top().first;
                        if (kPipeFine && pipe_rank_counter < effective_threshold) { tryPipePrefetch(nid); pipe_rank_counter++; }
                    }
                } else if (cache_->isInCache(nblock)) {
                    const float* nvec = cache_->getNodeVector(nid);'''
))

# Site 2: pending PQ (cache-miss path)
patches.append((
    '''                            if (!top_candidates.empty()) lowerBound = top_candidates.top().first;
                        }
                    } else {
                        const float* nvec = cache_->getNodeVector(pn.neighborId);
                        if (!nvec) continue;
                        float dist = l2Distance(query, nvec);
                        if (top_candidates.size() < ef || lowerBound > dist) {
                            candidate_set.emplace(dist, pn.neighborId);
                            top_candidates.emplace(dist, pn.neighborId);
                            if (top_candidates.size() > ef) top_candidates.pop();
                            if (!top_candidates.empty()) lowerBound = top_candidates.top().first;
                        }
                    }
                }
            }
            continue;''',
    '''                            if (!top_candidates.empty()) lowerBound = top_candidates.top().first;
                            if (kPipeFine && pipe_rank_counter < effective_threshold) { tryPipePrefetch(pn.neighborId); pipe_rank_counter++; }
                        }
                    } else {
                        const float* nvec = cache_->getNodeVector(pn.neighborId);
                        if (!nvec) continue;
                        float dist = l2Distance(query, nvec);
                        if (top_candidates.size() < ef || lowerBound > dist) {
                            candidate_set.emplace(dist, pn.neighborId);
                            top_candidates.emplace(dist, pn.neighborId);
                            if (top_candidates.size() > ef) top_candidates.pop();
                            if (!top_candidates.empty()) lowerBound = top_candidates.top().first;
                        }
                    }
                }
            }
            continue;'''
))

# Site 3: fast path PQ hybrid
patches.append((
    '''                    if (!top_candidates.empty()) {
                        lowerBound = top_candidates.top().first;
                    }
                    // 投机预取: top_candidates 的 miss blocks 周期性提交, I/O 被后续搜索掩盖''',
    '''                    if (!top_candidates.empty()) {
                        lowerBound = top_candidates.top().first;
                    }
                    if (kPipeFine && pipe_rank_counter < effective_threshold) { tryPipePrefetch(neighborId); pipe_rank_counter++; }
                    // 投机预取: top_candidates 的 miss blocks 周期性提交, I/O 被后续搜索掩盖'''
))

# Site 4: pending fast path PQ
patches.append((
    '''                // 预取完成后，用 getCachedBlockById 快速访问
                for (const auto& pn : pending_neighbors) {
                    if (pq_enabled_) {
                        float dist = pqDistance(query, pn.neighborId);
                        if (top_candidates.size() < ef || lowerBound > dist) {
                            candidate_set.emplace(dist, pn.neighborId);
                            top_candidates.emplace(dist, pn.neighborId);
                            if (top_candidates.size() > ef) {
                                top_candidates.pop();
                            }
                            if (!top_candidates.empty()) {
                                lowerBound = top_candidates.top().first;
                            }
                        }
                    } else {
                        CachedBlock* nBlock = cache_->getCachedBlockById(pn.blockId);
                        if (!nBlock) continue;''',
    '''                // 预取完成后，用 getCachedBlockById 快速访问
                for (const auto& pn : pending_neighbors) {
                    if (pq_enabled_) {
                        float dist = pqDistance(query, pn.neighborId);
                        if (top_candidates.size() < ef || lowerBound > dist) {
                            candidate_set.emplace(dist, pn.neighborId);
                            top_candidates.emplace(dist, pn.neighborId);
                            if (top_candidates.size() > ef) {
                                top_candidates.pop();
                            }
                            if (!top_candidates.empty()) {
                                lowerBound = top_candidates.top().first;
                            }
                            if (kPipeFine && pipe_rank_counter < effective_threshold) { tryPipePrefetch(pn.neighborId); pipe_rank_counter++; }
                        }
                    } else {
                        CachedBlock* nBlock = cache_->getCachedBlockById(pn.blockId);
                        if (!nBlock) continue;'''
))

# 10. Add pipe_ring_ env vars + reap logic in Phase B
patches.append((
    '''            static const bool kProfFine = std::getenv("PROFILE_FINE") && std::atoi(std::getenv("PROFILE_FINE")) != 0;''',
    '''            static const bool kProfFine = std::getenv("PROFILE_FINE") && std::atoi(std::getenv("PROFILE_FINE")) != 0;
            // I/O Pipelining env vars (BEH-021/022/023 draft)
            static const bool kPipeFine = std::getenv("PIPE_FINE") && std::atoi(std::getenv("PIPE_FINE")) != 0;
            static const bool kPipeL4 = std::getenv("PIPE_L4") && std::atoi(std::getenv("PIPE_L4")) != 0;
            static const bool kPipeL1 = std::getenv("PIPE_L1") && std::atoi(std::getenv("PIPE_L1")) != 0;'''
))

# 11. Add pipe_ring_ reap + L1 prefetch lambda after io_cands collection
patches.append((
    '''                if (cross) pages_needed.insert(page0 + 1);
            }

            if (kFinePread && !kFineDirect) {''',
    '''                if (cross) pages_needed.insert(page0 + 1);
            }

            // ---- I/O Pipelining: reap pipe_ring_ completions (BEH-021 draft) ----
            std::unordered_map<uint32_t, const char*> pipe_page_buf;
            int pipe_hits = 0;
            if (kPipeFine && pipe_ring_) {
                std::vector<IoUring::CqeResult> cqe_results;
                pipe_ring_->reapCompletions(cqe_results);
                for (const auto& cqe : cqe_results) {
                    uint32_t pg = (uint32_t)(cqe.user_data & 0xFFFFFFFFu);
                    int bidx = (int)(cqe.user_data >> 32) - 1;
                    if (cqe.res != 4096 || bidx < 0) {
                        if (bidx >= 0) pipe_ring_->freeBuffer(bidx);
                        continue;
                    }
                    pipe_page_buf[pg] = (const char*)pipe_ring_->getBuffer(bidx);
                }
                pipe_hits = pipe_page_buf.size();
                if (pipe_hits > 0) {
                    fprintf(stderr, "[PipeFine] pipe_hits=%d (piped=%zu)\\n",
                            pipe_hits, piped_pages.size());
                }
            }

            // L1/L2/L3 CPU Cache prefetch (BEH-022 draft, PIPE_L1=1)
            constexpr int kVecBytes = 512;
            constexpr int kCacheLines = (kVecBytes + 63) / 64;
            auto prefetchVecL1 = [&](const char* vec_ptr) {
                if (kPipeL1) {
                    for (int i = 0; i < kCacheLines; i++) {
                        _mm_prefetch(vec_ptr + i * 64, _MM_HINT_T0);
                    }
                }
            };

            if (kFinePread && !kFineDirect) {'''
))

# 12. pread path: check pipe_page_buf first
patches.append((
    '''                for (uint32_t pg : pages_needed) {
                    auto buf = std::make_unique<char[]>(4096);
                    ssize_t r = pread(vec_blocks_fd_, buf.get(), 4096, (off_t)pg << 12);
                    if (r == 4096) page_cache[pg] = std::move(buf);
                }''',
    '''                for (uint32_t pg : pages_needed) {
                    auto pit = pipe_page_buf.find(pg);
                    if (pit != pipe_page_buf.end()) {
                        auto buf = std::make_unique<char[]>(4096);
                        std::memcpy(buf.get(), pit->second, 4096);
                        page_cache[pg] = std::move(buf);
                        continue;
                    }
                    auto buf = std::make_unique<char[]>(4096);
                    ssize_t r = pread(vec_blocks_fd_, buf.get(), 4096, (off_t)pg << 12);
                    if (r == 4096) page_cache[pg] = std::move(buf);
                }'''
))

# 13. pread path: L1 prefetch in consider loop
patches.append((
    '''                char tmp_vec_pread[512];
                for (const auto& c : io_cands) {
                    auto it0 = page_cache.find(c.page0);
                    if (it0 == page_cache.end()) continue;
                    const char* p0 = it0->second.get();
                    const float* vec;
                    if (!c.cross) {
                        vec = reinterpret_cast<const float*>(p0 + c.oip);
                    } else {
                        auto it1 = page_cache.find(c.page0 + 1);
                        if (it1 == page_cache.end()) continue;
                        size_t first = 4096 - c.oip;
                        std::memcpy(tmp_vec_pread, p0 + c.oip, first);
                        std::memcpy(tmp_vec_pread + first, it1->second.get(), dim_ * sizeof(float) - first);
                        vec = reinterpret_cast<const float*>(tmp_vec_pread);
                    }
                    consider(c.nid, vec);''',
    '''                char tmp_vec_pread[512];
                for (size_t ci = 0; ci < io_cands.size(); ci++) {
                    const auto& c = io_cands[ci];
                    auto it0 = page_cache.find(c.page0);
                    if (it0 == page_cache.end()) continue;
                    const char* p0 = it0->second.get();
                    const float* vec;
                    if (!c.cross) {
                        vec = reinterpret_cast<const float*>(p0 + c.oip);
                    } else {
                        auto it1 = page_cache.find(c.page0 + 1);
                        if (it1 == page_cache.end()) continue;
                        size_t first = 4096 - c.oip;
                        std::memcpy(tmp_vec_pread, p0 + c.oip, first);
                        std::memcpy(tmp_vec_pread + first, it1->second.get(), dim_ * sizeof(float) - first);
                        vec = reinterpret_cast<const float*>(tmp_vec_pread);
                    }
                    if (kPipeL1 && ci + 1 < io_cands.size()) {
                        auto it_next = page_cache.find(io_cands[ci+1].page0);
                        if (it_next != page_cache.end()) prefetchVecL1(it_next->second.get() + io_cands[ci+1].oip);
                    }
                    consider(c.nid, vec);'''
))

# 14. io_uring path: skip pages already in pipe_page_buf
patches.append((
    '''            while (pit != pages_needed.end()) {
                uint32_t p0 = *pit;
                size_t len = 4096;''',
    '''            while (pit != pages_needed.end()) {
                uint32_t p0 = *pit;
                if (pipe_page_buf.count(p0)) { ++pit; continue; }
                size_t len = 4096;'''
))

# 15. io_uring path: L1 prefetch in consider loop
patches.append((
    '''            for (const auto& c : io_cands) {
                const char* p0 = getPagePtr(c.page0);
                if (!p0) continue;
                const float* vec;
                if (!c.cross) {
                    vec = reinterpret_cast<const float*>(p0 + c.oip);
                } else {
                    const char* p1 = getPagePtr(c.page0 + 1);
                    if (!p1) continue;
                    size_t first = 4096 - c.oip;
                    std::memcpy(tmp_vec, p0 + c.oip, first);
                    std::memcpy(tmp_vec + first, p1, dim_ * sizeof(float) - first);
                    vec = reinterpret_cast<const float*>(tmp_vec);
                }
                consider(c.nid, vec);''',
    '''            for (size_t ci = 0; ci < io_cands.size(); ci++) {
                const auto& c = io_cands[ci];
                const char* p0 = getPagePtr(c.page0);
                if (!p0) continue;
                const float* vec;
                if (!c.cross) {
                    vec = reinterpret_cast<const float*>(p0 + c.oip);
                } else {
                    const char* p1 = getPagePtr(c.page0 + 1);
                    if (!p1) continue;
                    size_t first = 4096 - c.oip;
                    std::memcpy(tmp_vec, p0 + c.oip, first);
                    std::memcpy(tmp_vec + first, p1, dim_ * sizeof(float) - first);
                    vec = reinterpret_cast<const float*>(tmp_vec);
                }
                if (kPipeL1 && ci + 1 < io_cands.size()) {
                    const char* next_p = getPagePtr(io_cands[ci+1].page0);
                    if (next_p) prefetchVecL1(next_p + io_cands[ci+1].oip);
                }
                consider(c.nid, vec);'''
))

# Apply all patches
for i, (old, new) in enumerate(patches):
    if old not in c:
        print(f"PATCH {i+1}: NOT FOUND", file=sys.stderr)
        sys.exit(1)
    c = c.replace(old, new, 1)
    print(f"PATCH {i+1}: OK")

with open(fpath, 'w') as f:
    f.write(c)
print(f"\nAll {len(patches)} patches applied to {fpath}")

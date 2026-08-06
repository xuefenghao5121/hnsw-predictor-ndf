#!/bin/bash
# cgroup_utils.sh - cgroup v1/v2 兼容工具库
#
# 核心原则: 严格隔离, 不允许任何偷用内存的行为被遗漏
# - 自动检测 cgroup v1/v2
# - 统一接口屏蔽差异
# - 严格 OOM/violation 检测 (failcnt > 0 即视为违规)
# - 全量统计: anon + file + slab + peak + failcnt
#
# 用法: source scripts/cgroup_utils.sh

set -euo pipefail

# ============================================================================
# 全局状态
# ============================================================================
export CG_VERSION=""        # "v1" 或 "v2"
export CG_ROOT=""           # cgroup 根路径
export CG_NAME=""           # 当前 cgroup 名称
export CG_PATH=""           # 当前 cgroup 完整路径
export CG_LIMIT_BYTES=0     # 内存限制 (bytes)

# ============================================================================
# 检测 cgroup 版本
# ============================================================================
cg_detect_version() {
    # 环境变量强制覆盖 (用于测试)
    if [ "${CGROUP_FORCE_V1:-0}" = "1" ]; then
        echo "v1"
        return
    fi

    local fstype
    fstype=$(stat -f -c '%T' /sys/fs/cgroup/ 2>/dev/null || echo "unknown")

    if [ "$fstype" = "cgroup2fs" ]; then
        echo "v2"
    elif [ -d /sys/fs/cgroup/memory ]; then
        # hybrid 模式: v1 和 v2 共存时, 优先 v1 (保守: v2 的 memory controller 可能未启用)
        echo "v1"
    else
        echo "unknown"
    fi
}

# ============================================================================
# 初始化 cgroup 环境
# 用法: cg_init <name> <limit_mb>
# ============================================================================
cg_init() {
    CG_NAME="$1"
    local limit_mb="$2"
    CG_LIMIT_BYTES=$((limit_mb * 1024 * 1024))

    CG_VERSION=$(cg_detect_version)
    case "$CG_VERSION" in
        v2)
            CG_ROOT="/sys/fs/cgroup"
            CG_PATH="$CG_ROOT/$CG_NAME"
            ;;
        v1)
            CG_ROOT="/sys/fs/cgroup/memory"
            CG_PATH="$CG_ROOT/$CG_NAME"
            ;;
        *)
            echo "[cgroup_utils] ERROR: 无法检测 cgroup 版本" >&2
            echo "[cgroup_utils] /sys/fs/cgroup/ 不是 cgroup2fs, 也无 memory/ 子目录" >&2
            return 1
            ;;
    esac

    echo "[cgroup_utils] 版本: $CG_VERSION | 路径: $CG_PATH | 限制: ${limit_mb}MB"
}

# ============================================================================
# 创建 cgroup
# ============================================================================
cg_create() {
    sudo mkdir -p "$CG_PATH"

    case "$CG_VERSION" in
        v1)
            # v1: 禁用 swap 以确保严格内存隔离
            echo 0 | sudo tee "$CG_PATH/memory.swappiness" > /dev/null 2>&1 || true
            # v1: 启用 OOM 控制 (不自动 kill, 但记录事件)
            # 不禁用 oom_kill (默认行为: 超限即 kill), 确保违规被捕获
            ;;
    esac
}

# ============================================================================
# 设置内存限制
# ============================================================================
cg_set_limit() {
    local limit_mb="$1"
    CG_LIMIT_BYTES=$((limit_mb * 1024 * 1024))

    case "$CG_VERSION" in
        v2)
            echo "$CG_LIMIT_BYTES" | sudo tee "$CG_PATH/memory.max" > /dev/null
            ;;
        v1)
            echo "$CG_LIMIT_BYTES" | sudo tee "$CG_PATH/memory.limit_in_bytes" > /dev/null
            # v1: 同时设置 swap 限制为 0 (禁止 swap)
            echo 0 | sudo tee "$CG_PATH/memory.memsw.limit_in_bytes" > /dev/null 2>&1 || true
            ;;
    esac
}

# ============================================================================
# 获取当前内存用量 (bytes)
# 返回: anon_bytes file_bytes total_bytes (三行)
# ============================================================================
cg_get_memory() {
    case "$CG_VERSION" in
        v2)
            local total anon file
            total=$(cat "$CG_PATH/memory.current" 2>/dev/null || echo 0)
            anon=$(grep "^anon " "$CG_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
            file=$(grep "^file " "$CG_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
            echo "${anon:-0}"
            echo "${file:-0}"
            echo "$total"
            ;;
        v1)
            local total anon file
            total=$(cat "$CG_PATH/memory.usage_in_bytes" 2>/dev/null || echo 0)
            # v1 stat 字段映射
            local anon_active anon_inactive file_active file_inactive
            anon_active=$(grep "^total_active_anon " "$CG_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
            anon_inactive=$(grep "^total_inactive_anon " "$CG_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
            file_active=$(grep "^total_active_file " "$CG_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
            file_inactive=$(grep "^total_inactive_file " "$CG_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
            anon=$(( ${anon_active:-0} + ${anon_inactive:-0} ))
            file=$(( ${file_active:-0} + ${file_inactive:-0} ))
            echo "$anon"
            echo "$file"
            echo "$total"
            ;;
    esac
}

# ============================================================================
# 获取内存峰值 (bytes)
# ============================================================================
cg_get_peak() {
    case "$CG_VERSION" in
        v2)
            cat "$CG_PATH/memory.peak" 2>/dev/null || echo 0
            ;;
        v1)
            cat "$CG_PATH/memory.max_usage_in_bytes" 2>/dev/null || echo 0
            ;;
    esac
}

# ============================================================================
# 检查 OOM / 内存违规
# 返回: 违规次数 (0 = 干净, >0 = 有违规)
# ============================================================================
cg_check_violations() {
    case "$CG_VERSION" in
        v2)
            # v2: memory.events 中的 oom_kill 是真正的 OOM kill
            # oom (不含 _kill) 是 OOM 事件 (包括被避免了 kill 的)
            # 两者都 > 0 表示有内存违规
            local oom oom_kill
            oom=$(grep "^oom " "$CG_PATH/memory.events" 2>/dev/null | awk '{print $2}')
            oom_kill=$(grep "^oom_kill " "$CG_PATH/memory.events" 2>/dev/null | awk '{print $2}')
            echo "$(( ${oom:-0} + ${oom_kill:-0} ))"
            ;;
        v1)
            # v1: memory.failcnt 是超过限制的次数
            # 任何 failcnt > 0 都表示有内存分配被拒绝 = 偷用内存未遂
            # 这比只看 oom_kill 更严格
            local failcnt
            failcnt=$(cat "$CG_PATH/memory.failcnt" 2>/dev/null || echo 0)
            echo "$failcnt"
            ;;
    esac
}

# ============================================================================
# 获取完整统计摘要 (统一格式, 屏蔽 v1/v2 差异)
# 输出格式: key: value (每行一个)
# ============================================================================
cg_stats_summary() {
    local mem_output
    mem_output=$(cg_get_memory)
    local anon file total
    anon=$(echo "$mem_output" | head -1)
    file=$(echo "$mem_output" | sed -n '2p')
    total=$(echo "$mem_output" | sed -n '3p')

    local peak violations
    peak=$(cg_get_peak)
    violations=$(cg_check_violations)

    # 统一格式输出
    echo "anon_bytes:           $anon"
    echo "file_bytes:           $file"
    echo "total_bytes:          $total"
    echo "peak_bytes:           $peak"
    echo "limit_bytes:          $CG_LIMIT_BYTES"
    echo "violations:           $violations"

    # 详细统计 (版本特定字段, 用于调试)
    case "$CG_VERSION" in
        v2)
            local refault majfault pgfault slab
            refault=$(grep "^workingset_refault_file " "$CG_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
            majfault=$(grep "^pgmajfault " "$CG_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
            pgfault=$(grep "^pgfault " "$CG_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
            slab=$(grep "^slab " "$CG_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
            echo "workingset_refault:   ${refault:-0}"
            echo "pgmajfault:           ${majfault:-0}"
            echo "pgfault:              ${pgfault:-0}"
            echo "slab_bytes:           ${slab:-0}"
            # OOM 事件明细
            echo "--- memory.events ---"
            cat "$CG_PATH/memory.events" 2>/dev/null | grep -E "^(oom|oom_kill) " || true
            ;;
        v1)
            local refault majfault pgfault
            refault=$(grep "^workingset_refault " "$CG_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
            majfault=$(grep "^total_pgmajfault " "$CG_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
            pgfault=$(grep "^total_pgfault " "$CG_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
            echo "workingset_refault:   ${refault:-0}"
            echo "pgmajfault:           ${majfault:-0}"
            echo "pgfault:              ${pgfault:-0}"
            # v1 额外信息
            echo "--- v1 specific ---"
            echo "failcnt:              $(cat "$CG_PATH/memory.failcnt" 2>/dev/null || echo '?')"
            echo "usage_in_bytes:       $(cat "$CG_PATH/memory.usage_in_bytes" 2>/dev/null || echo '?')"
            echo "max_usage_in_bytes:   $(cat "$CG_PATH/memory.max_usage_in_bytes" 2>/dev/null || echo '?')"
            ;;
    esac
}

# ============================================================================
# 将进程加入 cgroup
# ============================================================================
cg_add_proc() {
    local pid="$1"
    echo "$pid" | sudo tee "$CG_PATH/cgroup.procs" > /dev/null
}

# ============================================================================
# 后台内存监控 (持续采样, 用于检测峰值)
# 用法: cg_start_monitor <output_file>
# 返回: 监控进程 PID (用于后续 kill)
# ============================================================================
# 注意: 不能用 MONITOR_PID=$(cg_start_monitor ...) 因为 $() 会等待
# 所有子进程退出 (包括后台循环), 导致永远挂起.
# 正确用法: cg_start_monitor logfile  (后台 PID 写入 $CG_MONITOR_PID)
cg_start_monitor() {
    local logfile="$1"
    echo "" > "$logfile"
    (
        while true; do
            local ts mem_output cur anon file
            ts=$(date +%s%N)
            mem_output=$(cg_get_memory)
            anon=$(echo "$mem_output" | head -1)
            file=$(echo "$mem_output" | sed -n '2p')
            cur=$(echo "$mem_output" | sed -n '3p')
            echo "$ts $cur $anon $file" >> "$logfile"
            sleep 0.1
        done
    ) &
    CG_MONITOR_PID=$!
}

# ============================================================================
# 停止后台监控
# ============================================================================
cg_stop_monitor() {
    local pid="$1"
    kill "$pid" 2>/dev/null || true
}

# ============================================================================
# 严格验证 (测试后调用)
# 检查: peak ≤ limit, violations = 0
# 返回: 0 = 通过, 1 = 违规
# ============================================================================
cg_verify() {
    local peak violations
    peak=$(cg_get_peak)
    violations=$(cg_check_violations)

    local pass=0

    # 检查 1: 峰值不能超过限制
    if [ "$peak" -gt "$CG_LIMIT_BYTES" ]; then
        echo "[cgroup_utils] ❌ PEAK 违规: peak=${peak} > limit=${CG_LIMIT_BYTES}" >&2
        pass=1
    fi

    # 检查 2: 不能有任何 OOM/violation 事件
    if [ "$violations" -gt 0 ]; then
        echo "[cgroup_utils] ❌ OOM 违规: violations=${violations}" >&2
        pass=1
    fi

    if [ "$pass" -eq 0 ]; then
        echo "[cgroup_utils] ✅ 严格隔离通过: peak=${peak} ≤ limit=${CG_LIMIT_BYTES}, violations=0"
    fi

    return $pass
}

# ============================================================================
# 清理 cgroup
# ============================================================================
cg_destroy() {
    # v1: 需要移到回 root cgroup
    # v2: rmdir 即可 (进程需先移出)
    sudo rmdir "$CG_PATH" 2>/dev/null || true
}

# ============================================================================
# drop caches (清空全局 page cache)
# ============================================================================
cg_drop_caches() {
    sync
    echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null
}

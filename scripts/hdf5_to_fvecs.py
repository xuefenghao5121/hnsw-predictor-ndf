#!/usr/bin/env python3
"""
hdf5_to_fvecs.py - HDF5 → fvecs/bvecs 格式转换

支持 ann-benchmarks 标准 HDF5 格式:
  /train     (N, D) float32  → base.fvecs
  /test      (Q, D) float32  → query.fvecs
  /neighbors (Q, K) int32    → gt.bin (benchmark GT 格式)
  /distances (Q, K) float32  → (可选, 不转换)

也支持自定义 dataset 名称 (通过 --keys 指定)。

用法:
  # 标准转换 (ann-benchmarks 格式)
  python3 scripts/hdf5_to_fvecs.py data/sift-128-euclidean.hdf5 --prefix sift1m

  # 自定义 dataset 名称
  python3 scripts/hdf5_to_fvecs.py data/custom.hdf5 --prefix custom \
      --base-key vectors --query-key queries

  # 转换到指定目录
  python3 scripts/hdf5_to_fvecs.py data/glove.hdf5 --prefix glove --out-dir data/

输出文件:
  <prefix>_base.fvecs       — base 向量 (fvecs 格式)
  <prefix>_query.fvecs      — query 向量 (fvecs 格式, 如有)
  <prefix>_gt10.bin         — Ground Truth (benchmark 格式, 如有 neighbors)

fvecs 格式: 每条记录 = [dim:int32] + [dim×float32]
GT bin 格式: header [n_queries:u32 + K:u32] + n_queries×K×uint64
"""

import numpy as np
import h5py
import struct
import sys
import os
import argparse


def write_fvecs(path, data):
    """写 fvecs 文件。data: (N, D) float32 numpy array."""
    n, d = data.shape
    with open(path, 'wb') as f:
        for i in range(n):
            f.write(struct.pack('i', d))
            f.write(data[i].astype(np.float32).tobytes())
    print(f"  ✅ {path}: {n}×{d} float32 ({os.path.getsize(path) / 1024 / 1024:.1f} MB)")


def write_gt_bin(path, neighbors, k):
    """写 GT bin 文件 (benchmark 格式)。
    neighbors: (Q, K) int array (0-based).
    只写前 k 列。"""
    q, k_available = neighbors.shape
    k_actual = min(k, k_available)
    with open(path, 'wb') as f:
        f.write(struct.pack('II', q, k_actual))
        for i in range(q):
            ids = neighbors[i, :k_actual].astype(np.uint64)
            f.write(ids.tobytes())
    print(f"  ✅ {path}: {q}×{k_actual} uint64 GT ({os.path.getsize(path) / 1024:.0f} KB)")


def inspect_hdf5(path):
    """打印 HDF5 文件结构。"""
    print(f"\n📂 {path} 结构:")
    with h5py.File(path, 'r') as f:
        def visitor(name, obj):
            if isinstance(obj, h5py.Dataset):
                print(f"  /{name}: shape={obj.shape}, dtype={obj.dtype}")
        f.visititems(visitor)
        # 检查 attrs
        for k, v in f.attrs.items():
            print(f"  (attr) {k}: {v}")


def main():
    parser = argparse.ArgumentParser(description='HDF5 → fvecs/GT 转换')
    parser.add_argument('hdf5_path', help='HDF5 文件路径')
    parser.add_argument('--prefix', required=True, help='输出文件前缀 (如 sift1m)')
    parser.add_argument('--out-dir', default='.', help='输出目录 (默认当前目录)')
    parser.add_argument('--base-key', default=None,
                        help='base 向量 dataset 名称 (默认自动检测: train/data/vectors)')
    parser.add_argument('--query-key', default=None,
                        help='query 向量 dataset 名称 (默认自动检测: test/query/queries)')
    parser.add_argument('--gt-key', default=None,
                        help='GT dataset 名称 (默认自动检测: neighbors/ground_truth)')
    parser.add_argument('--k', type=int, default=10, help='GT top-K (默认 10)')
    parser.add_argument('--inspect', action='store_true', help='仅检查文件结构, 不转换')
    args = parser.parse_args()

    if not os.path.exists(args.hdf5_path):
        print(f"❌ 文件不存在: {args.hdf5_path}")
        sys.exit(1)

    # 检查结构
    inspect_hdf5(args.hdf5_path)

    if args.inspect:
        return

    os.makedirs(args.out_dir, exist_ok=True)

    with h5py.File(args.hdf5_path, 'r') as f:
        # 自动检测 dataset 名称
        def find_key(candidates, explicit):
            if explicit:
                if explicit in f:
                    return explicit
                # 支持嵌套路径
                if explicit.lstrip('/') in f:
                    return explicit.lstrip('/')
                print(f"  ⚠️ 指定的 key '{explicit}' 不存在")
                return None
            for c in candidates:
                if c in f:
                    return c
            return None

        base_key = find_key(['train', 'data', 'vectors'], args.base_key)
        query_key = find_key(['test', 'query', 'queries'], args.query_key)
        gt_key = find_key(['neighbors', 'ground_truth'], args.gt_key)

        if base_key is None:
            print("❌ 找不到 base 向量 dataset (尝试了 train/data/vectors)")
            print("   请用 --base-key 指定 dataset 名称")
            sys.exit(1)

        # 转换 base
        print(f"\n🔄 转换 /{base_key} → fvecs...")
        base_data = f[base_key][:].astype(np.float32)
        write_fvecs(os.path.join(args.out_dir, f"{args.prefix}_base.fvecs"), base_data)

        # 转换 query
        if query_key:
            print(f"\n🔄 转换 /{query_key} → fvecs...")
            query_data = f[query_key][:].astype(np.float32)
            write_fvecs(os.path.join(args.out_dir, f"{args.prefix}_query.fvecs"), query_data)
        else:
            print("\n⚠️ 无 query 数据, 跳过 query 转换")

        # 转换 GT
        if gt_key:
            print(f"\n🔄 转换 /{gt_key} → GT bin (K={args.k})...")
            neighbors = f[gt_key][:]
            write_gt_bin(os.path.join(args.out_dir, f"{args.prefix}_gt{args.k}.bin"),
                         neighbors, args.k)
        else:
            print("⚠️ 无 GT 数据, 跳过 GT 转换")

    print(f"\n✅ 转换完成!")
    print(f"   下一步: bash scripts/build_pipeline.sh {args.out_dir}/{args.prefix}_base.fvecs {args.prefix} <M> {args.out_dir}/{args.prefix}_query.fvecs {args.k}")


if __name__ == '__main__':
    main()

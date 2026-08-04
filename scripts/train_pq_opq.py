#!/usr/bin/env python3
"""
train_pq_opq.py - 训练 OPQ+PQ 编码 (优化旋转矩阵 + PQ)

OPQ 通过学习旋转矩阵 R 使子空间更独立，在不增大 codes 的前提下提升 PQ 质量。
输出: PQ codes 文件 (PQCO 格式，与 benchmark 兼容) + 旋转后的 query 文件

用法:
  python3 scripts/train_pq_opq.py <base.fvecs> <query.fvecs> <output_pq.bin> <output_query_rotated.fvecs> [M]
  # 例:
  python3 scripts/train_pq_opq.py data/deep10m_base.fvecs data/deep10m_query.fvecs output/pqco_deep10m_opq_m32.bin data/deep10m_query_opq.fvecs 32
"""

import numpy as np
import faiss
import sys
import os
import struct


def load_fvecs(path):
    with open(path, 'rb') as f:
        dim = struct.unpack('i', f.read(4))[0]
    raw = np.fromfile(path, dtype=np.int32)
    row = dim + 1
    assert raw.size % row == 0
    n = raw.size // row
    data = raw.reshape(n, row)[:, 1:].view(np.float32)
    return np.ascontiguousarray(data, dtype=np.float32)


def save_fvecs(path, data):
    n, d = data.shape
    with open(path, 'wb') as f:
        for i in range(n):
            f.write(struct.pack('i', d))
            f.write(data[i].astype(np.float32).tobytes())


def main():
    if len(sys.argv) < 5:
        print("Usage: python3 train_pq_opq.py <base.fvecs> <query.fvecs> <output_pq.bin> <output_query_rotated.fvecs> [M]")
        sys.exit(1)

    base_path = sys.argv[1]
    query_path = sys.argv[2]
    output_pq = sys.argv[3]
    output_query = sys.argv[4]
    M = int(sys.argv[5]) if len(sys.argv) >= 6 else 32

    train_data = load_fvecs(base_path)
    query_data = load_fvecs(query_path)
    n, d = train_data.shape
    nbits = 8
    dsub = d // M

    print(f"OPQ+PQ: M={M}, dsub={dsub}, n={n}, d={d}")

    # ---- Train OPQ + PQ ----
    print("Training OPQ rotation matrix...")
    opq = faiss.OPQMatrix(d, M)
    opq.train(train_data)
    
    # Apply rotation to base data
    print("Applying OPQ rotation to base data...")
    base_rotated = opq.apply(train_data)
    base_rotated = np.ascontiguousarray(base_rotated, dtype=np.float32)

    # Train PQ on rotated data
    print("Training PQ on rotated data...")
    pq = faiss.ProductQuantizer(d, M, nbits)
    pq.train(base_rotated)

    print("Encoding all vectors...")
    codes = np.ascontiguousarray(pq.compute_codes(base_rotated))

    # ---- Reconstruction error ----
    ns = min(2000, n)
    idx = np.random.choice(n, ns, replace=False)
    recon = pq.decode(codes[idx])
    mse = np.mean(np.sum((base_rotated[idx] - recon) ** 2, axis=1))
    base_energy = np.mean(np.sum(base_rotated[idx] ** 2, axis=1))
    print(f"  Reconstruction MSE: {mse:.2f} (relative {mse / base_energy * 100:.2f}%)")

    # ---- Save PQ codes (standard PQCO format, rotated space) ----
    os.makedirs(os.path.dirname(output_pq) or ".", exist_ok=True)
    codebook = faiss.vector_to_array(pq.centroids).reshape(M, 256, dsub)
    with open(output_pq, 'wb') as f:
        f.write(b'PQCO')
        f.write(struct.pack('Q', n))
        f.write(struct.pack('I', M))
        f.write(struct.pack('I', nbits))
        f.write(struct.pack('I', d))
        f.write(struct.pack('III', M, 256, dsub))
        f.write(codebook.astype(np.float32).tobytes())
        f.write(codes.tobytes())
    print(f"Saved PQ codes: {output_pq} ({os.path.getsize(output_pq) / 1e6:.1f} MB)")

    # ---- Rotate queries and save ----
    print("Rotating queries...")
    query_rotated = opq.apply(query_data)
    query_rotated = np.ascontiguousarray(query_rotated, dtype=np.float32)
    save_fvecs(output_query, query_rotated)
    print(f"Saved rotated queries: {output_query} ({os.path.getsize(output_query) / 1e6:.1f} MB)")

    # ---- ADC accuracy check ----
    print("\nADC accuracy check...")
    n_test = min(1000, n)
    index_pq = faiss.IndexPQ(d, M, nbits)
    index_pq.pq = pq
    index_pq.is_trained = True
    index_pq.add(base_rotated)
    queries = base_rotated[:n_test]
    _, I_adc = index_pq.search(queries, 10)

    overlap = 0.0
    for i in range(n_test):
        diff = base_rotated - queries[i]
        true_top = np.argpartition(np.sum(diff * diff, axis=1), 10)[:10]
        overlap += len(set(true_top.tolist()) & set(I_adc[i].tolist())) / 10
    print(f"  ADC top-10 overlap: {overlap / n_test * 100:.1f}%")

    print("\n✅ OPQ+PQ training complete")


if __name__ == "__main__":
    main()

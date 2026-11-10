# Tối ưu hóa hiệu năng ký số DSA bằng tiền tính toán — đánh giá thực nghiệm với RSA

Toàn bộ DSA và RSA được tự cài bằng Python thuần (lũy thừa modulo, Euclid mở rộng, Miller–Rabin, sinh tham số, ký/xác minh).
PyCryptodome chỉ dùng trong test để kiểm tra chéo tính đúng; `pow()` có sẵn của Python chỉ dùng làm mốc tham chiếu.

Giải thích đầy đủ về ý tưởng, công thức, từng file, từng hàm, cách đo và kết quả nằm trong **GIAI_THICH.md**.

## Chạy nhanh

```bash
pip install -r requirements.txt
python3 main.py test      # 11 test (~50 s)
python3 main.py demo      # demo; thêm --level 3072 cho mức 3072
python3 main.py bench     # E1–E5 (~20 phút); chạy riêng: python3 main.py bench e1 e3
python3 main.py plots     # vẽ lại biểu đồ vào bench/plots/
python3 main.py params    # sinh lại tham số -> core/params.json (~20 s)
python3 main.py all       # test -> demo -> bench -> plots
```

Bằng Docker:

```bash
docker build -t dsa-precompute .
docker run --rm dsa-precompute demo
```

Yêu cầu Python ≥ 3.8. Mọi lệnh chạy từ thư mục gốc của repo.

## Các biến thể

| Mã | Biến thể | File |
| --- | --- | --- |
| V0 | DSA baseline: k ngẫu nhiên, g^k bằng square-and-multiply, k⁻¹ bằng Euclid | `dsa/dsa.py` (`BaselineSigner`) |
| V1 | Pool tiền tính toán (k, k⁻¹, r), lấp bằng cách của V0 | `dsa/pool.py`, `PoolSigner` |
| V2 | Fixed-base windowing cho g^k | `dsa/fixed_base.py` (`FixedBaseWindow`) |
| V3 | Comb Lim–Lee cho g^k | `dsa/fixed_base.py` (`CombLimLee`) |
| V4 | Pool lấp bằng comb/window + nghịch đảo hàng loạt (Montgomery trick) | `dsa/pool.py` (`batch_inverse=True`) |
| R0 | RSA PKCS#1 v1.5 (SHA-256), số mũ đầy đủ | `rsa/rsa.py` |
| R1 | RSA-CRT (Garner) | `rsa/rsa.py` (`crt=True`) |

## Cấu trúc

```
core/    modarith.py (modexp, egcd, modinv, batch_inv) · primes.py (Miller–Rabin, sinh p,q,g và khóa RSA) · keystore.py · params.json
dsa/     dsa.py (ký/xác minh, V0–V4) · pool.py (PrecomputePool) · fixed_base.py (window, comb)
rsa/     rsa.py (R0, R1)
tests/   test_all.py — 11 test: đúng/sai, pool không cấp trùng k (8 thread), lấp nền, kiểm tra chéo PyCryptodome
bench/   harness.py · run_all.py (E1–E5) · plots.py · results/*.csv · plots/*.png
demo/    demo_cli.py
```

## Lưu ý

- `core/params.json` chứa khóa **thử nghiệm** dùng chung cho benchmark, không dùng cho mục đích thật.
- Python không chạy constant-time: kết quả chỉ nói về hiệu năng, không nói về khả năng chống side-channel.
- FIPS 186-5 (2023) không còn chấp thuận DSA để tạo chữ ký mới; kỹ thuật tiền tính toán ở đây áp dụng y nguyên cho ECDSA/Schnorr.

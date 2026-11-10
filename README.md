# Tối ưu hóa hiệu năng ký số DSA bằng tiền tính toán — đánh giá thực nghiệm với RSA

Các thuật toán DSA và RSA được cài bằng Python, gồm lũy thừa modulo, Euclid mở rộng, Miller–Rabin, sinh tham số, ký và xác minh.
PyCryptodome chỉ dùng trong test để kiểm tra chéo tính đúng. `pow()` có sẵn của Python được dùng làm mốc tham chiếu, kiểm tra kết quả và tăng tốc sinh tham số/khóa; đường ký/xác minh mặc định dùng `modexp` tự cài.

Giải thích về ý tưởng, công thức, từng file, từng hàm, cách đo và kết quả nằm trong [GIAI_THICH.md](GIAI_THICH.md).

## Chạy nhanh

```bash
git clone https://github.com/minh-phuong0104/dsa-precompute.git
cd dsa-precompute
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py test
python main.py demo
```

Trên Windows, kích hoạt môi trường bằng `.venv\Scripts\activate` (cmd) hoặc `.venv\Scripts\Activate.ps1` (PowerShell).

| Lệnh | Chức năng |
| --- | --- |
| `python main.py test` | Chạy 11 test, gồm kiểm tra chéo PyCryptodome |
| `python main.py demo --level 3072` | Demo mức 3072; mặc định là 2048 |
| `python main.py bench` | Chạy E1–E5, ghi kết quả vào `bench/results/` |
| `python main.py bench e1 e3` | Chỉ chạy E1 và E3 |
| `python main.py plots` | Vẽ lại 5 biểu đồ trong `bench/plots/` từ CSV có sẵn |
| `python main.py params` | Sinh lại tham số và khóa, ghi đè `core/params.json` |
| `python main.py all` | Chạy lần lượt test → demo → bench → plots |

Repo đã có `core/params.json`, nên không cần chạy `params` trước khi test/demo. Thời gian chạy phụ thuộc cấu hình máy; benchmark đầy đủ có thể mất hàng chục phút. Benchmark ghi đè các CSV tương ứng và `env.json`; sau khi đổi tham số/khóa, cần chạy lại benchmark và biểu đồ để có kết quả tương ứng.

Bằng Docker:

```bash
docker build -t dsa-precompute .
docker run --rm dsa-precompute demo
```

Yêu cầu Python ≥ 3.8. Mọi lệnh chạy từ thư mục gốc của repo. Docker dùng Python 3.12; muốn giữ kết quả mới trên máy host, gắn thư mục `bench/results/` và `bench/plots/` vào container.

## Các biến thể

| Mã | Biến thể | File |
| --- | --- | --- |
| V0 | DSA baseline: k ngẫu nhiên, g^k bằng square-and-multiply, k⁻¹ bằng Euclid | `dsa/dsa.py` (`BaselineSigner`) |
| V1 | Pool tiền tính toán (k, k⁻¹, r), lấp bằng cách của V0 | `dsa/dsa.py` (`PoolSigner`), `dsa/pool.py` (`PrecomputePool`) |
| V2 | Fixed-base windowing cho g^k | `dsa/dsa.py` (`FixedBaseSigner`), `dsa/fixed_base.py` (`FixedBaseWindow`) |
| V3 | Comb Lim–Lee cho g^k | `dsa/dsa.py` (`FixedBaseSigner`), `dsa/fixed_base.py` (`CombLimLee`) |
| V4 | Pool lấp bằng comb/window + nghịch đảo hàng loạt (Montgomery trick) | `dsa/dsa.py` (`PoolSigner`, `batch_inverse=True`), `dsa/pool.py` |
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
- Theo [FIPS 186-5](https://doi.org/10.6028/NIST.FIPS.186-5), DSA chỉ được giữ lại để xác minh chữ ký đã có, không tạo chữ ký mới.
- Ý tưởng bảng fixed-base có thể chuyển sang phép nhân điểm của ECDSA/Schnorr. Pool nonce cần thiết kế riêng theo từng lược đồ; không áp dụng nguyên xi cho ECDSA tất định ([RFC 6979](https://www.rfc-editor.org/rfc/rfc6979.html#section-3.2)) hoặc EdDSA ([RFC 8032](https://www.rfc-editor.org/rfc/rfc8032.html#section-5.1.6)), vì nonce phụ thuộc thông điệp.

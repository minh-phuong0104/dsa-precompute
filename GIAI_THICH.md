# Giải thích toàn bộ dự án

**Đề tài:** Tối ưu hóa hiệu năng ký số DSA bằng kỹ thuật tiền tính toán và đánh giá thực nghiệm với RSA

Code trong repo không có comment. File này thay cho comment: nó giải thích ý tưởng, công thức, từng file, từng hàm, cách kiểm thử, cách đo và cách đọc kết quả.

## Mục lục

1. Ý tưởng của đề tài
2. Cấu trúc thư mục và cách chạy
3. Nền tảng toán học (`core/`)
4. DSA cơ bản (`dsa/dsa.py`)
5. Các kỹ thuật tối ưu V1–V4 (`dsa/pool.py`, `dsa/fixed_base.py`)
6. RSA và RSA-CRT (`rsa/rsa.py`)
7. Kiểm thử (`tests/test_all.py`)
8. Đo hiệu năng (`bench/`)
9. Kết quả thực nghiệm
10. Phân tích bảo mật
11. Demo, `main.py`, Docker
12. Tra cứu nhanh từng hàm
13. Tài liệu tham khảo

---

## 1. Ý tưởng của đề tài

Một chữ ký DSA gồm hai số (r, s):

```
r = (g^k mod p) mod q            không phụ thuộc thông điệp, rất tốn (lũy thừa modulo p, 2048–3072 bit)
s = k⁻¹ · (H(m) + x·r) mod q     phụ thuộc thông điệp, rất rẻ (vài phép nhân modulo q, 224–256 bit)
```

Hầu hết chi phí nằm ở `g^k mod p`, và phần này tính được **trước khi có thông điệp**. Đề tài khai thác điều đó theo hai hướng:

| Hướng | Cách làm | Biến thể |
| --- | --- | --- |
| Dời thời điểm tính | Tính sẵn bộ (k, k⁻¹, r) lúc máy rảnh, cất vào pool | V1 |
| Làm phép tính rẻ hơn | g cố định nên lập bảng lũy thừa của g một lần, sau đó tra bảng | V2 (window), V3 (comb) |
| Kết hợp | Lấp pool bằng bảng fixed-base + nghịch đảo hàng loạt | V4 |

RSA được dùng làm mốc so sánh (R0, R1). Pool bộ (k, k⁻¹, r) của DSA không áp dụng trực tiếp cho RSA, vì `s = m^d mod n` phụ thuộc thông điệp. RSA-CRT vẫn tính trước các tham số `dp`, `dq`, `qinv` để dùng lại khi ký.

Các thuật toán DSA và RSA được cài bằng Python. Các công cụ hỗ trợ gồm:
- **PyCryptodome:** chỉ dùng trong test, để kiểm tra chéo rằng chữ ký của nhóm đúng chuẩn.
- **`pow()` có sẵn của Python** (viết bằng C): dùng làm mốc tham chiếu, kiểm tra kết quả và tăng tốc sinh tham số/khóa.
- **Matplotlib:** vẽ biểu đồ từ CSV; không tham gia thuật toán ký/xác minh.

---

## 2. Cấu trúc thư mục và cách chạy

```
dsa-precompute/
├── main.py              lệnh chạy chung: params | test | demo | bench | plots | all
├── requirements.txt     pycryptodome, matplotlib
├── Dockerfile           đóng gói chạy bằng Docker
├── README.md            hướng dẫn ngắn
├── GIAI_THICH.md        file này
├── core/
│   ├── modarith.py      lũy thừa modulo, Euclid mở rộng, nghịch đảo, nghịch đảo hàng loạt
│   ├── primes.py        Miller–Rabin, sinh số nguyên tố, sinh tham số DSA, sinh khóa RSA
│   ├── keystore.py      sinh một lần rồi nạp lại tham số/khóa từ params.json
│   └── params.json      tham số DSA và khóa RSA THỬ NGHIỆM dùng chung cho mọi phép đo
├── dsa/
│   ├── dsa.py           tham số, khóa, ký, xác minh, các Signer V0–V4
│   ├── pool.py          PrecomputePool: kho các bộ (k, k⁻¹, r)
│   └── fixed_base.py    FixedBaseWindow (V2) và CombLimLee (V3)
├── rsa/
│   └── rsa.py           RSA PKCS#1 v1.5: ký thường (R0), ký CRT (R1), xác minh
├── tests/
│   └── test_all.py      11 test tính đúng
├── bench/
│   ├── harness.py       hàm đo chung, ghi CSV, ghi thông tin máy
│   ├── run_all.py       5 thí nghiệm E1–E5
│   ├── plots.py         vẽ biểu đồ
│   ├── results/         CSV kết quả, env.json
│   └── plots/           5 biểu đồ PNG
└── demo/
    └── demo_cli.py      demo trên dòng lệnh
```

### Cách chạy

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py test
python main.py demo
python main.py bench
python main.py plots
```

Các tùy chọn chạy từng thí nghiệm, demo mức 3072 và lệnh `all` nằm trong [README.md](README.md). Thời gian chạy phụ thuộc máy. Repo đã có khóa thử nghiệm; `python main.py params` sinh lại và ghi đè khóa, nên chỉ chạy khi cần rồi đo lại benchmark và vẽ lại biểu đồ.

Với Docker:

```bash
docker build -t dsa-precompute .
docker run --rm dsa-precompute demo
docker run --rm dsa-precompute test
```

Yêu cầu Python 3.8 trở lên, và mọi lệnh phải chạy từ thư mục gốc của repo.

---

## 3. Nền tảng toán học (`core/`)

### 3.1 Lũy thừa modulo — `modexp(base, exp, mod)`

Đây là thuật toán square-and-multiply, duyệt các bit của số mũ từ trái sang phải:

```
result = 1
với mỗi bit b của exp (từ bit cao nhất đến bit thấp nhất):
    result = result² mod m
    nếu b = 1:  result = result · base mod m
```

**Vì sao đúng:** sau khi đọc xong một tiền tố e' của số mũ, ta có `result = base^e'`. Đọc thêm một bit b thì tiền tố mới là `2e' + b`, nên phải bình phương rồi nhân thêm `base^b`.

**Chi phí** với số mũ dài t bit: t phép bình phương cộng trung bình t/2 phép nhân, tức khoảng **1,5·t phép nhân modulo**.

| Thao tác | Số mũ | Số phép nhân ở mức 2048 |
| --- | --- | --- |
| DSA ký | k, 224 bit | ≈ 336 |
| DSA xác minh | u₁ và u₂, mỗi số 224 bit | ≈ 672 |
| RSA ký R0 | d, 2048 bit | ≈ 3072 |
| RSA xác minh | e = 65537, 17 bit, 2 bit bằng 1 | 19 trong `modexp` hiện tại |

Bảng này giải thích trước hai kết quả đo: DSA ký nhanh hơn RSA ký (số mũ ngắn hơn khoảng 9 lần), còn RSA xác minh nhanh hơn DSA xác minh (e rất nhỏ).

Code còn xử lý hai trường hợp biên: `mod == 1` thì trả về 0, và số mũ âm thì đổi thành nghịch đảo lũy thừa số mũ dương.

### 3.2 Euclid mở rộng và nghịch đảo — `egcd`, `modinv`

`egcd(a, b)` trả về (g, x, y) sao cho `a·x + b·y = g = gcd(a, b)`. Thuật toán dùng dạng lặp, mỗi bước cập nhật:

```
(a, b)   ← (b, a mod b)
(x₀, x₁) ← (x₁, x₀ − ⌊a/b⌋·x₁)
(y₀, y₁) ← (y₁, y₀ − ⌊a/b⌋·y₁)
```

`modinv(a, m)`: nếu `gcd(a, m) = 1` thì `a·x ≡ 1 (mod m)`, nên `a⁻¹ = x mod m`. Nếu gcd khác 1 thì không tồn tại nghịch đảo, và hàm báo lỗi.

### 3.3 Nghịch đảo hàng loạt — `batch_inv(values, m)` (Montgomery trick)

Bài toán: cần nghịch đảo n số a₁, …, aₙ. Thay vì chạy Euclid n lần, cách này chỉ chạy Euclid **1 lần**:

```
Bước 1, tích tiền tố:   c₁ = a₁,   cᵢ = cᵢ₋₁ · aᵢ
Bước 2, nghịch đảo một lần duy nhất:   inv = cₙ⁻¹
Bước 3, đi ngược từ i = n về 2:
            aᵢ⁻¹ = inv · cᵢ₋₁
            inv  = inv · aᵢ          (lúc này inv = cᵢ₋₁⁻¹)
        cuối cùng:  a₁⁻¹ = inv
```

Bước 3 đúng vì `cᵢ⁻¹ · cᵢ₋₁ = (cᵢ₋₁·aᵢ)⁻¹ · cᵢ₋₁ = aᵢ⁻¹`.

Chi phí lý tưởng: 1 lần Euclid cộng 3(n − 1) phép nhân. Cài đặt hiện tại khởi tạo `acc = 1` rồi nhân cả phần tử đầu, nên với n > 0 thực hiện 3n − 2 phép nhân modulo; n = 0 trả về danh sách rỗng.

**Ví dụ** mod 11, với các số 7, 3, 5:

| Bước | Tính toán | Kết quả |
| --- | --- | --- |
| Tích tiền tố | 7; 7·3 = 21 ≡ 10; 10·5 = 50 ≡ 6 | c = (7, 10, 6) |
| Nghịch đảo một lần | 6⁻¹ mod 11 | 2 (vì 6·2 = 12 ≡ 1) |
| i = 3 | 5⁻¹ = 2·10 = 20 ≡ 9; inv = 2·5 ≡ 10 | 5·9 = 45 ≡ 1 ✓ |
| i = 2 | 3⁻¹ = 10·7 = 70 ≡ 4; inv = 10·3 ≡ 8 | 3·4 = 12 ≡ 1 ✓ |
| i = 1 | 7⁻¹ = 8 | 7·8 = 56 ≡ 1 ✓ |

### 3.4 Kiểm tra nguyên tố Miller–Rabin — `is_probable_prime(n, rounds)`

1. Loại ngay các số nhỏ và các số chia hết cho một số nguyên tố dưới 2000 (danh sách `SMALL_PRIMES`).
2. Viết `n − 1 = 2^s · d` với d lẻ.
3. Mỗi vòng, chọn ngẫu nhiên a trong [2, n − 2] và tính `x = a^d mod n`. Nếu x = 1 hoặc x = n − 1 thì vòng này qua. Nếu không, bình phương x tối đa s − 1 lần; nếu gặp n − 1 thì qua. Nếu không bao giờ gặp n − 1 thì n chắc chắn là hợp số.
4. Xác suất một hợp số qua được k vòng không quá 4^(−k). Nhóm dùng 40 vòng cho q và cho số nguyên tố RSA, 20 vòng cho p của DSA.

`random_prime(bits)` sinh số ngẫu nhiên bằng `secrets`, ép bit cao nhất bằng 1 (để có đủ độ dài) và bit thấp nhất bằng 1 (để là số lẻ), rồi lặp đến khi gặp số nguyên tố.

### 3.5 Sinh tham số DSA — `gen_dsa_params(L, N)`

```
q = số nguyên tố N bit
lặp:
    X = số ngẫu nhiên L bit
    p = X − (X mod 2q) + 1          ⇒ p − 1 chia hết cho 2q, nên q | p − 1
    dừng khi p dài đúng L bit và p là số nguyên tố
e = (p − 1) / q
g = h^e mod p với h = 2, 3, … cho đến khi g > 1
```

Vì `g^q = h^(p−1) = 1 (mod p)` (định lý Fermat nhỏ) và q là số nguyên tố, nên khi g ≠ 1 thì g có bậc đúng bằng q. Cách sinh p theo cấu trúc của FIPS 186, nhưng không kèm seed để người khác kiểm chứng lại.

### 3.6 Sinh khóa RSA — `gen_rsa_key(bits, e=65537)`

Sinh hai số nguyên tố p, q, mỗi số bits/2 bit, khác nhau, sao cho `n = p·q` dài đúng `bits` bit. Tính `φ = (p−1)(q−1)` và `d = e⁻¹ mod φ`. Nếu e không khả nghịch modulo φ thì sinh lại.

### 3.7 Kho khóa — `core/keystore.py`

- `LEVELS = {"2048": (2048, 224), "3072": (3072, 256)}`: hai mức bảo mật tương đương với RSA-2048 (112 bit) và RSA-3072 (128 bit), theo NIST SP 800-57.
- `generate()`: sinh tham số DSA, khóa DSA và khóa RSA cho cả hai mức, ghi ra `params.json` dưới dạng hex, kèm thời gian sinh.
- `load()`: đọc `params.json` (nếu chưa có thì tự sinh), trả về `(dsa_keys, rsa_keys, gen_seconds)`.

Mục đích: mọi biến thể và mọi lần chạy đều dùng **cùng một bộ tham số và khóa**, nên kết quả so sánh được với nhau.

---

## 4. DSA cơ bản (`dsa/dsa.py`)

### 4.1 Dữ liệu

- `DSAParams(p, q, g)`, có thêm hai thuộc tính `L = số bit của p` và `N = số bit của q`.
- `DSAKey(params, x, y)`: x là khóa bí mật, `y = g^x mod p` là khóa công khai.

### 4.2 Các phép toán

```
keygen:      x ← ngẫu nhiên trong [1, q−1],   y = g^x mod p
hash_to_int: z = N bit trái nhất của SHA-256(m)   (theo FIPS 186)

Ký:          k ← ngẫu nhiên trong [1, q−1]
             r = (g^k mod p) mod q
             s = k⁻¹ · (z + x·r) mod q
             nếu r = 0 hoặc s = 0 thì chọn k khác

Xác minh:    kiểm tra 0 < r < q và 0 < s < q
             w  = s⁻¹ mod q
             u₁ = z·w mod q
             u₂ = r·w mod q
             v  = (g^u₁ · y^u₂ mod p) mod q
             hợp lệ  ⇔  v = r
```

**Vì sao xác minh đúng:** từ công thức của s ta có `k = s⁻¹(z + x·r) = u₁ + x·u₂ (mod q)`. Vì g có bậc q nên `g^u₁ · y^u₂ = g^(u₁ + x·u₂) = g^k (mod p)`, do đó v = r.

### 4.3 Ví dụ tính tay

Tham số: p = 23, q = 11 (22 chia hết cho 11), h = 2 nên g = 2² = 4. Kiểm tra: 4¹¹ mod 23 = 1.

Khóa: x = 3, suy ra y = 4³ mod 23 = 64 mod 23 = **18**.

**Ký** với z = 5, chọn k = 7:

| Đại lượng | Tính | Giá trị |
| --- | --- | --- |
| g^k mod p | 4⁷ mod 23 | 8 |
| r | 8 mod 11 | **8** |
| k⁻¹ mod q | 7·8 = 56 = 5·11 + 1 | 8 |
| s | 8·(5 + 3·8) = 232 mod 11 | **1** |

**Xác minh** chữ ký (8, 1):

| Đại lượng | Tính | Giá trị |
| --- | --- | --- |
| w | 1⁻¹ mod 11 | 1 |
| u₁, u₂ | 5·1, 8·1 | 5, 8 |
| g^u₁ mod p | 4⁵ mod 23 | 12 |
| y^u₂ mod p | 18⁸ mod 23 | 16 |
| v | 12·16 = 192 mod 23 = 8; 8 mod 11 | **8 = r → hợp lệ** |

### 4.4 Thiết kế lớp Signer

Mọi biến thể DSA đều có cùng một giao diện `sign(msg) → (r, s)`. Chúng chỉ khác nhau ở **cách lấy bộ (k, k⁻¹, r)**:

```
Signer.sign(msg):
    lặp:
        (k, k⁻¹, r) = self.fresh_triple()      ← mỗi biến thể cài khác nhau
        bỏ qua nếu r = 0
        s = k⁻¹ · (z + x·r) mod q               ← hàm _finish, dùng chung cho mọi biến thể
        trả về (r, s) nếu s ≠ 0
```

| Lớp | Cách `fresh_triple` lấy (k, k⁻¹, r) | Biến thể |
| --- | --- | --- |
| `BaselineSigner(key, expfn)` | k ngẫu nhiên, k⁻¹ bằng Euclid, r bằng `expfn` (mặc định `modexp` tự cài; truyền `pow` để có mốc tham chiếu C) | V0 |
| `FixedBaseSigner(key, "window", w)` | như V0, nhưng g^k tính bằng bảng window | V2 |
| `FixedBaseSigner(key, "comb", h)` | như V0, nhưng g^k tính bằng bảng comb | V3 |
| `PoolSigner(key, filler, batch_inverse=False)` | lấy từ pool; pool cạn thì gọi `filler` (fallback) | V1 |
| `PoolSigner(key, FixedBaseSigner(...), batch_inverse=True)` | lấy từ pool đã lấp bằng fixed-base + nghịch đảo hàng loạt | V4 |

Thiết kế này bảo đảm mọi biến thể dùng chung một hàm tính s và một hàm xác minh. Vì vậy chênh lệch thời gian đo được chỉ đến từ cách lấy (k, k⁻¹, r).

---

## 5. Các kỹ thuật tối ưu

### 5.1 V1 — Pool tiền tính toán (`dsa/pool.py`, lớp `PrecomputePool`)

```
OFFLINE (lúc máy rảnh): lặp
    (k, k⁻¹, r) ← filler.fresh_triple()
    đưa vào hàng đợi

ONLINE (khi thông điệp m đến):
    (k, k⁻¹, r) ← lấy ra khỏi hàng đợi       (mỗi bộ dùng ĐÚNG MỘT lần)
    s = k⁻¹ · (H(m) + x·r) mod q
```

Ở ví dụ mục 4.3, pool lưu sẵn bộ (7, 8, 8). Khi thông điệp đến, chỉ còn tính `s = 8·(z + 24) mod 11`.

**Chi phí online:** 1 lần SHA-256 cộng 2 phép nhân modulo q (224 bit), thay cho khoảng 336 phép nhân modulo p (2048 bit) và một lần Euclid.

**Các hàm:**

| Hàm | Việc làm |
| --- | --- |
| `__init__(params, filler, batch_inverse, capacity)` | tạo hàng đợi `deque`, một `Lock`, bộ đếm `issued`, cờ dừng cho thread nền |
| `_make_batch(n)` | tạo n bộ. Nếu không bật nghịch đảo hàng loạt thì gọi `filler.fresh_triple()` n lần. Nếu bật thì sinh n giá trị k, tính r bằng `filler.engine.pow` (hoặc `filler.expfn`), rồi tính cả n nghịch đảo bằng `batch_inv` |
| `fill(n=None, batch=256)` | lấp thêm n bộ (mặc định lấp đến đầy) theo từng lô `batch`, mỗi lô thêm vào dưới lock |
| `take()` | lấy một bộ bằng `popleft()` dưới lock; trả về `None` khi pool rỗng |
| `start_background(low_water, batch)` | chạy một thread nền tự lấp khi pool xuống dưới `capacity × low_water` |
| `stop_background()` | dừng thread nền |
| `__len__` | số bộ còn trong pool |

**Bảo đảm khi nhiều thread rút từ pool:** `popleft()` nằm trong `with self._lock`, nên mỗi phần tử hàng đợi chỉ được cấp một lần. Test `test_no_k_issued_twice_under_threads` kiểm tra không có k trùng trong lần chạy với 2000 bộ. Việc sinh k vẫn là ngẫu nhiên, không có cơ chế loại trùng toàn cục, nên test không chứng minh k không bao giờ lặp giữa mọi lần sinh.

**Fallback:** khi `take()` trả về `None`, `PoolSigner` gọi thẳng `filler.fresh_triple()` và tăng bộ đếm `fallbacks`. Nhờ vậy phép ký không bao giờ bị chặn, và benchmark biết được có bao nhiêu chữ ký đã phải tính trực tiếp.

### 5.2 V2 — Fixed-base windowing (`FixedBaseWindow`)

**Ý tưởng:** viết k theo cơ số 2^w, tức chia k thành d = ⌈N/w⌉ chữ số, mỗi chữ số dài w bit:

```
k = k₀ + k₁·2^w + k₂·2^(2w) + … + k_(d−1)·2^((d−1)w),     0 ≤ kᵢ < 2^w

⇒  g^k = ∏ g^(kᵢ · 2^(w·i))
```

**Bảng tính trước** (hàm `__init__`):

```
T[i][j] = g^(j · 2^(w·i)) mod p,     i = 0…d−1,   j = 0…2^w − 1
```

Cách dựng: hàng i bắt đầu với `base = g^(2^(w·i))`; mỗi phần tử `T[i][j] = T[i][j−1] · base`. Phần tử cuối hàng là `base^(2^w − 1)`; nhân thêm một lần `base` nữa thì được `base^(2^w)`, chính là cơ số của hàng tiếp theo.

**Tính g^k** (hàm `pow`): lấy lần lượt từng chữ số bằng `k & mask` rồi dịch k sang phải w bit:

```
g^k = T[0][k₀] · T[1][k₁] · … · T[d−1][k_(d−1)] mod p
```

Chi phí: **d = ⌈N/w⌉ phép nhân, không có phép bình phương nào.** Chữ số bằng 0 thì bỏ qua phép nhân.

| | Số phép nhân, N = 224 | Số phần tử bảng | Dung lượng bảng ở mức 2048 |
| --- | --- | --- | --- |
| Square-and-multiply | ≈ 336 | 0 | 0 |
| Window w = 4 | 56 | 56 × 16 = 896 | ≈ 210 KB |
| Window w = 8 | 28 | 28 × 256 = 7168 | ≈ 1,8 MB |

Dung lượng mỗi phần tử khoảng L/8 byte (256 byte ở mức 2048).

**Ví dụ** với p = 23, g = 4, k = 7, w = 2:
- 7 viết theo cơ số 4: 7 = 3 + 1·4, nên k₀ = 3, k₁ = 1.
- T[0][3] = 4³ mod 23 = 18. T[1][1] = 4⁴ mod 23 = 3.
- g⁷ = 18·3 = 54 mod 23 = **8**, khớp với mục 4.3.

### 5.3 V3 — Comb Lim–Lee (`CombLimLee`)

**Ý tưởng:** xếp N bit của k thành h hàng, mỗi hàng dài a = ⌈N/h⌉ bit. Hàng j chứa các bit từ j·a đến j·a + a − 1. Sau đó đọc theo **cột**.

**Bảng tính trước:**

```
gⱼ = g^(2^(j·a)) mod p,      j = 0…h−1          (gⱼ₊₁ = gⱼ bình phương a lần)
G[u] = ∏ gⱼ  lấy trên các bit j đang bật trong u,     u = 0…2^h − 1
```

Bảng G được dựng nhanh: lấy bit thấp nhất của u (`low = u & −u`, ứng với chỉ số j), rồi `G[u] = G[u xor low] · gⱼ`. Mỗi phần tử chỉ tốn 1 phép nhân.

**Tính g^k:** duyệt các cột i từ a − 1 về 0:

```
result = result²
u = (bit i của hàng 0) | (bit i của hàng 1) << 1 | … | (bit i của hàng h−1) << (h−1)
nếu u ≠ 0:  result = result · G[u]
```

**Vì sao đúng:** `k = Σⱼ Σᵢ bit(j·a + i) · 2^(j·a + i)`, nên `g^k = ∏ᵢ (∏ⱼ gⱼ^bit(j·a+i))^(2^i) = ∏ᵢ G[uᵢ]^(2^i)`. Vòng lặp chính là sơ đồ Horner theo i.

**Chi phí:** a phép bình phương cộng a phép nhân. Với N = 224 và h = 8: 28 + 28 = 56 phép.

**Bảng:** chỉ 2^h phần tử. Với h = 8: 256 phần tử ≈ **64 KB**, nhỏ hơn bảng window w = 8 khoảng 28 lần.

**Ví dụ** với p = 23, g = 4, k = 7 = 0111₂, h = 2, a = 2:
- Hàng 0 gồm bit 0 và 1: (1, 1). Hàng 1 gồm bit 2 và 3: (1, 0).
- g₀ = 4, g₁ = 4^(2²) = 4⁴ mod 23 = 3. Bảng: G[1] = 4, G[2] = 3, G[3] = 12.
- Cột i = 1: u = (bit 1 = 1) | (bit 3 = 0) << 1 = 1. result = 1² · G[1] = 4.
- Cột i = 0: u = (bit 0 = 1) | (bit 2 = 1) << 1 = 3. result = 4² · 12 = 192 mod 23 = **8**, đúng kết quả.

**So sánh window và comb:** ở cùng giá trị w = h, comb chậm hơn window khoảng 2 lần (vì có thêm phép bình phương), nhưng bảng nhỏ hơn ⌈N/w⌉ lần. Ở cùng tốc độ, comb tiết kiệm bộ nhớ hơn (mục 9.3).

Cả hai lớp đều có hai thuộc tính `entries` (số phần tử bảng) và `table_bytes` (tổng số byte biểu diễn các số nguyên), dùng trong E3. `table_bytes` không tính phần bộ nhớ quản lý của đối tượng `int` và `list` trong Python, nên không phải tổng RAM thực tế.

### 5.4 V4 — Pool kết hợp

```
OFFLINE: sinh một lô n giá trị k
    rᵢ   = (g^kᵢ mod p) mod q        ← tính bằng window hoặc comb
    kᵢ⁻¹                            ← cả lô tính bằng batch_inv (1 lần Euclid)
ONLINE:  giống V1
```

Trong code, V4 chính là `PoolSigner(key, FixedBaseSigner(...), batch_inverse=True)`.

---

## 6. RSA và RSA-CRT (`rsa/rsa.py`)

### 6.1 Khóa — `RSAKey(n, e, d, p, q)`

```
n = p·q,   φ(n) = (p−1)(q−1),   e = 65537,   d = e⁻¹ mod φ(n)
```

Hàm `__post_init__` tính sẵn các giá trị cho CRT: `dp = d mod (p−1)`, `dq = d mod (q−1)`, `qinv = q⁻¹ mod p`, và `k` = độ dài n tính bằng byte.

### 6.2 Đệm thông điệp — `emsa_pkcs1_v15(msg, k)`

Theo RFC 8017, mục 9.2:

```
T  = DigestInfo(SHA-256) ‖ SHA-256(msg)          (DigestInfo là 19 byte cố định: SHA256_PREFIX)
EM = 0x00 ‖ 0x01 ‖ 0xFF…0xFF ‖ 0x00 ‖ T            (tổng cộng k byte, ít nhất 8 byte 0xFF)
m  = EM đổi thành số nguyên
```

### 6.3 Ký và xác minh

```
R0:          s = m^d mod n

R1 (CRT):    s₁ = m^dp mod p
             s₂ = m^dq mod q
             h  = qinv · (s₁ − s₂) mod p
             s  = s₂ + h·q                    (công thức Garner)

Xác minh:    độ dài chữ ký = k byte, s < n, và s^e mod n = EM
```

**Vì sao CRT đúng:** theo Fermat nhỏ, `m^d ≡ m^(d mod (p−1)) = s₁ (mod p)`, và tương tự với q. Công thức Garner ghép hai đồng dư đó thành số duy nhất trong [0, n): `s ≡ s₂ (mod q)` hiển nhiên đúng, và `s ≡ s₂ + (s₁ − s₂) = s₁ (mod p)`.

**Vì sao CRT nhanh hơn khoảng 4 lần:** chi phí một phép lũy thừa tỉ lệ với (độ dài số mũ) × (độ dài modulo)², tức khoảng L³. CRT thay một phép cỡ L bằng hai phép cỡ L/2: `2 × (1/2)³ = 1/4`.

**Ví dụ** với p = 5, q = 11, n = 55, e = 3, d = 27 (vì 3·27 = 81 ≡ 1 mod 40), m = 2:

| Đại lượng | Tính | Giá trị |
| --- | --- | --- |
| dp, dq, qinv | 27 mod 4; 27 mod 10; 11⁻¹ mod 5 | 3, 7, 1 |
| s₁ | 2³ mod 5 | 3 |
| s₂ | 2⁷ mod 11 = 128 mod 11 | 7 |
| h | 1·(3 − 7) mod 5 | 1 |
| s | 7 + 1·11 | **18** |
| Kiểm tra | 18³ mod 55 = 5832 mod 55 | **2 = m ✓** |

PKCS#1 v1.5 là lược đồ **tất định**, nên R0 và R1 phải cho ra cùng một chữ ký, từng byte một. Test có kiểm tra điều này.

---

## 7. Kiểm thử (`tests/test_all.py`)

Chạy bằng `python3 main.py test`. Có 11 test, tất cả đều qua.

| Nhóm | Test | Kiểm tra gì |
| --- | --- | --- |
| Số học | `test_modexp_matches_pow` | `modexp` khớp `pow()` trên 200 bộ số ngẫu nhiên: modulo 2048 bit, số mũ 300 bit |
| Số học | `test_modinv_and_batch` | `batch_inv` khớp `modinv` trên 500 phần tử, và mọi tích a·a⁻¹ đều bằng 1 |
| Fixed-base | `test_window_and_comb_match_pow_1000_random_k` | window và comb khớp `pow(g, k, p)` với mọi w từ 2 đến 8, ở cả hai mức; riêng w = 6 thử 1000 giá trị k |
| DSA | `test_sign_verify_all_variants` | 6 cấu hình (V0 tự cài, V0 dùng `pow`, V2, V3, V1, V4) × 2 mức × 30 thông điệp: chữ ký đúng thì được chấp nhận; sửa thông điệp hoặc sửa s thì bị từ chối |
| DSA | `test_cross_check_pycryptodome` | chữ ký của mọi biến thể được `Crypto.Signature.DSS` của PyCryptodome xác minh; ngược lại, chữ ký do PyCryptodome tạo được `verify` của nhóm chấp nhận |
| Pool | `test_no_k_issued_twice_under_threads` | 8 thread cùng rút 2000 bộ từ pool: đủ 2000 bộ, không k nào trùng, pool rỗng ở cuối |
| Pool | `test_fallback_when_empty` | pool chứa 3 bộ, ký 6 lần: cả 6 chữ ký hợp lệ và `fallbacks = 3` |
| Pool | `test_triples_consistent` | mọi bộ trong pool V4 (mức 3072) thỏa k·k⁻¹ ≡ 1 và r = (g^k mod p) mod q |
| Pool | `test_background_fill` | thread nền tự lấp pool tới ngưỡng, sau đó ký 10 lần không cần fallback |
| RSA | `test_sign_verify_and_crt` | R0 và R1 cho cùng một chữ ký; chữ ký đúng được chấp nhận, sửa thông điệp thì bị từ chối |
| RSA | `test_cross_check_pycryptodome` | chữ ký R1 trùng từng byte với `pkcs1_15` của PyCryptodome; chữ ký R0 được PyCryptodome xác minh |

Hàm `all_signers(key)` tạo đủ 6 cấu hình DSA để các test dùng chung.

---

## 8. Đo hiệu năng (`bench/`)

### 8.1 Hàm đo chung — `harness.measure(fn, ...)`

1. Chạy `fn` một lần để ước lượng thời gian, rồi chọn số lần đo mỗi vòng M sao cho một vòng mất khoảng `budget_s` giây (M nằm trong khoảng [min_iter, max_iter]).
2. Chạy khởi động (warm-up) tối đa 50 lần, không ghi lại.
3. Đo 5 vòng, mỗi vòng M lần. Mỗi lần đo bằng `time.perf_counter_ns()` và đổi ra µs.
4. Trả về các chỉ số:
   - `median_us`: trung vị của toàn bộ mẫu. Đây là chỉ số chính.
   - `p95_us`: phân vị 95%, tức 95% số lần chạy nhanh hơn giá trị này.
   - `mean_us`: trung bình.
   - `rep_median_min_us`, `rep_median_max_us`: trung vị nhỏ nhất và lớn nhất trong 5 vòng, cho biết kết quả ổn định đến đâu.
   - `iters_per_rep`, `repeats`.

Nhóm dùng median thay vì trung bình vì median không bị kéo lệch bởi vài lần đo bất thường (hệ điều hành chen ngang, bộ thu gom rác của Python…).

Các công thức suy ra:

```
hệ số tăng tốc  = median(V0) / median(Vx)
chi phí mỗi bộ  = thời gian lấp pool / kích thước pool
thông lượng     = số chữ ký trong đợt / tổng thời gian của đợt
```

Các hàm khác: `write_csv(name, rows)` ghi kết quả ra `bench/results/`; `env_info()` ghi thông tin CPU, RAM, phiên bản Python vào `env.json`.

### 8.2 Các thí nghiệm — `bench/run_all.py`

Mọi thí nghiệm chạy ở cả hai mức 2048 và 3072. `W_BEST = 8` là giá trị w/h dùng cho V2, V3, V4.

**Đo trên chữ ký thật:** ở E1, hàm `checked(signer, key)` bọc signer lại, để mỗi lần đo ký một thông điệp khác nhau và lưu chữ ký. Sau khi đo, `verify_all` lấy mẫu khoảng 200 chữ ký để xác minh lại; benchmark dừng nếu mẫu có chữ ký sai. E3 đối chiếu một giá trị k với `pow()` cho mỗi bảng; E5 xác minh mẫu của đợt cuối. E4 đo ký/xác minh trên cùng một thông điệp, không dùng wrapper `checked`. Các kiểm tra mẫu bổ sung cho bộ test, không thay thế việc kiểm tra mọi kết quả.

| Thí nghiệm | Hàm | Đo gì | Cách đo | File CSV |
| --- | --- | --- | --- | --- |
| E1 | `e1()` | độ trễ ký online của V0 (tự cài), V0 (`pow`), V2, V3, V1, V4 | pool chứa 8000 bộ, nhiều hơn 50 + 5×1000 lần ký, nên chắc chắn không lần nào rơi về fallback (có `assert fallbacks == 0`) | `e1_sign_latency.csv` |
| E2 | `e2()` | chi phí lấp pool với 3 cách lấp × kích thước 100 / 1000 / 10 000 | lấy median của 3 lần chạy (1 lần với pool 10 000); thêm phép đo riêng phần nghịch đảo: Euclid từng số so với hàng loạt, trên 1000 số | `e2_pool_fill.csv` |
| E3 | `e3()` | thời gian g^k và dung lượng bảng của window và comb với w = 2…8 | so với square-and-multiply và `pow()`; mỗi bảng được kiểm tra một lần với `pow` trước khi đo | `e3_fixed_base.csv` |
| E4 | `e4()` | DSA (V0, V2, V4, xác minh) so với RSA (R0, R1, xác minh), sinh khóa, kích thước | hai lượt `modexp` tự cài và `pow()` C áp dụng cho DSA V0, DSA xác minh và RSA; DSA V2/V4 giữ nguyên engine fixed-base. Sinh khóa RSA lặp 10 lần (mức 2048) và 4 lần (mức 3072), lấy phần tử giữa phía trên sau khi sắp xếp | `e4_dsa_vs_rsa.csv` |
| E5 | `e5()` | thông lượng xử lý tuần tự một đợt 2000 yêu cầu ký | 5 trường hợp: V0, V3 không pool, V4 pool đầy, pool một nửa, pool rỗng; mỗi trường hợp chạy 3 lần, lấy median | `e5_burst.csv` |

### 8.3 Biểu đồ — `bench/plots.py`

Đọc các file CSV và vẽ 5 biểu đồ, mỗi biểu đồ có hai khung (mức 2048 và 3072):

| File | Dạng | Ghi chú |
| --- | --- | --- |
| `e1_sign_latency.png` | cột, trục log | vạch lỗi là p95; nhãn gồm thời gian và hệ số tăng tốc |
| `e2_pool_fill.png` | cột nhóm | ms mỗi bộ theo kích thước pool |
| `e3_fixed_base.png` | đường, trục log–log | thời gian theo dung lượng bảng; hai đường ngang là mốc square-and-multiply và `pow()` |
| `e4_dsa_vs_rsa.png` | cột, trục log | ms mỗi thao tác |
| `e5_burst.png` | thanh ngang, trục log | số chữ ký mỗi giây |

Trục log được dùng vì các giá trị chênh nhau tới 4 bậc độ lớn (từ µs đến chục ms).

---

## 9. Kết quả thực nghiệm

Máy đo: Intel Xeon 2,10 GHz, 2 lõi (máy ảo), RAM 8 GB, Linux, CPython 3.13.18. Các số dưới đây là median.

### 9.1 E1 — Độ trễ ký online

| Biến thể | Mức 2048 | Hệ số | Mức 3072 | Hệ số |
| --- | --- | --- | --- | --- |
| V0 (tự cài) | 4034 µs | 1,0× | 9604 µs | 1,0× |
| V0 (`pow` C) | 3174 µs | 1,3× | 7625 µs | 1,3× |
| V2 window w = 8 | 414 µs | 9,7× | 924 µs | 10,4× |
| V3 comb h = 8 | 729 µs | 5,5× | 1656 µs | 5,8× |
| V1 pool (online) | 2,1 µs | ≈ 1900× | 2,1 µs | ≈ 4500× |
| V4 pool (online) | 3,3 µs | ≈ 1200× | 2,2 µs | ≈ 4400× |

- Ký online với pool gần như không phụ thuộc mức bảo mật, vì chỉ còn là phép nhân modulo q.
- V1 và V4 đi qua cùng một đường ký online, nên chênh lệch giữa chúng ở thang micro-giây chỉ là nhiễu đo.
- Modexp tự cài chỉ chậm hơn `pow()` C khoảng 1,27 lần, nên các hệ số tăng tốc phản ánh thuật toán chứ không phải do Python chậm.

### 9.2 E2 — Chi phí lấp pool

| Cách lấp (mức 2048) | Mỗi bộ | Lấp 10 000 bộ |
| --- | --- | --- |
| V1: modexp + Euclid từng k | 4,06 ms | 40,6 s |
| V4: comb h = 8 + nghịch đảo hàng loạt | 0,73 ms | 7,3 s |
| V4: window w = 8 + nghịch đảo hàng loạt | 0,38 ms | 3,8 s |

Ở mức 3072, ba con số tương ứng là 9,76 ms, 1,69 ms và 0,87 ms mỗi bộ.

- Chi phí mỗi bộ gần như không đổi theo kích thước pool, tức thời gian lấp tăng tuyến tính.
- Riêng phần nghịch đảo: Euclid tốn 32,5 µs mỗi số, cách hàng loạt chỉ 1,2 µs (nhanh hơn 27 lần). Nhưng nghịch đảo chiếm chưa tới 1% chi phí mỗi bộ, nên lợi ích chính của V4 đến từ fixed-base.
- **Tổng chi phí của V4** (0,38 ms offline cộng 0,002 ms online) **gần bằng V2 tính trực tiếp** (0,41 ms). Pool không giảm tổng lượng tính toán; nó dời việc tính sang lúc máy rảnh.

### 9.3 E3 — Window và comb

| Mức | Cách tính g^k | Thời gian | Bảng | Tăng tốc |
| --- | --- | --- | --- | --- |
| 2048 | square-and-multiply | 3981 µs | 0 | 1,0× |
| 2048 | `pow()` C | 3097 µs | 0 | 1,3× |
| 2048 | comb h = 8 | 682 µs | 64 KB | 5,8× |
| 2048 | window w = 4 | 699 µs | 210 KB | 5,7× |
| 2048 | window w = 8 | 364 µs | 1,8 MB | 10,9× |
| 3072 | square-and-multiply | 9445 µs | 0 | 1,0× |
| 3072 | comb h = 8 | 1581 µs | 96 KB | 6,0× |
| 3072 | window w = 8 | 840 µs | 3,0 MB | 11,2× |

- Với window, tăng w thêm 1 làm thời gian giảm 13–23%, nhưng bảng lớn thêm 1,5–1,8 lần. Lợi ích giảm dần khi w tăng.
- Comb h = 8 nhanh ngang window w = 4, nhưng bảng nhỏ hơn 3,3 lần. Nên chọn window khi cần tốc độ tối đa và có dư vài MB bộ nhớ; chọn comb cho thiết bị ít bộ nhớ.
- Dựng bảng chỉ tốn 5–223 ms và làm một lần lúc khởi động.

### 9.4 E4 — DSA so với RSA

| Thao tác (modexp tự cài) | Mức 2048 | Mức 3072 |
| --- | --- | --- |
| DSA ký V0 | 4,03 ms | 9,61 ms |
| DSA ký V2 | 0,41 ms | 0,89 ms |
| DSA ký V4 (online) | 1,9 µs | 2,0 µs |
| RSA ký R0 | 36,2 ms | 113,0 ms |
| RSA ký R1 CRT | 11,1 ms | 33,5 ms |
| DSA xác minh | 8,00 ms | 19,99 ms |
| RSA xác minh | 0,19 ms | 0,40 ms |
| DSA sinh khóa (x, y) | 3,96 ms | 9,36 ms |
| RSA sinh khóa | 1,03 s | 5,13 s |
| DSA sinh tham số p, q, g (một lần) | 0,69 s | 6,65 s |
| Chữ ký DSA | 56 byte | 64 byte |
| Chữ ký RSA | 256 byte | 384 byte |

- **Ký:** DSA V0 đã nhanh hơn RSA-CRT 2,7 lần (mức 2048) và 3,5 lần (mức 3072). Với fixed-base, khoảng cách lên 27 và 38 lần.
- **CRT:** tăng tốc RSA 3,3–3,4 lần, gần mức 4 lần của lý thuyết.
- **Xác minh:** RSA nhanh hơn DSA 42 lần (mức 2048) và 50 lần (mức 3072).
- **Sinh khóa:** DSA nhanh hơn RSA rất nhiều, khi đã có tham số p, q, g dùng chung.
- **Kích thước:** chữ ký DSA nhỏ hơn RSA 4,6–6 lần.
- Đo bằng `pow()` C cho cùng kết luận định tính; số liệu đầy đủ có trong CSV.

### 9.5 E5 — Đợt 2000 yêu cầu ký

| Trường hợp | Mức 2048 | Mức 3072 |
| --- | --- | --- |
| V0 | 241 chữ ký/giây | 103 chữ ký/giây |
| V3 comb, không pool | 1207 | 589 |
| V4, pool đầy (2000 bộ) | ≈ 409 000 | ≈ 378 000 |
| V4, pool một nửa (1000 bộ) | 2576 | 1186 |
| V4, pool rỗng | 1289 | 582 |

Khi pool chỉ đầy một nửa, thông lượng chỉ gấp đôi pool rỗng: 1000 yêu cầu còn lại phải tính trực tiếp, và phần này chiếm gần hết thời gian. **Pool chỉ hấp thụ được những đợt tăng đột biến không vượt quá kích thước của nó.** Về lâu dài, tốc độ ký bền vững vẫn bị giới hạn bởi tốc độ lấp pool: khoảng 2600 bộ mỗi giây trên mỗi lõi (window w = 8, mức 2048).

### 9.6 Giới hạn của thực nghiệm

- Máy ảo 2 lõi chạy CPython: số tuyệt đối chậm hơn nhiều lần so với thư viện C như OpenSSL. Vì vậy nhóm chỉ kết luận dựa trên **tỉ lệ** giữa các biến thể cùng cài đặt.
- Không đo trường hợp thread nền lấp pool song song với luồng ký: GIL của CPython khiến hai luồng tranh nhau một lõi. Triển khai thật nên lấp pool ở một tiến trình riêng.
- Code không chạy constant-time, nên không đánh giá được chi phí phòng chống side-channel.

---

## 10. Phân tích bảo mật

### 10.1 Dùng lại k làm lộ khóa bí mật

Giả sử cùng một k được dùng để ký hai thông điệp z₁ và z₂. Hai chữ ký có cùng r, và:

```
s₁ − s₂ = k⁻¹ · (z₁ − z₂)  (mod q)
⇒  k = (z₁ − z₂) / (s₁ − s₂)  mod q
⇒  x = (s₁·k − z₁) / r  mod q        ← lộ khóa bí mật
```

Đây là lỗi đã làm lộ khóa ký của Sony PlayStation 3 năm 2010. Vì vậy pool phải cấp mỗi bộ **đúng một lần**: `take()` dùng `popleft()` dưới lock, và có test kiểm chứng với 8 thread.

### 10.2 k phải ngẫu nhiên đều

Chỉ cần lộ hoặc lệch vài bit của k qua nhiều chữ ký là đủ để khôi phục x bằng tấn công lattice (Hidden Number Problem). Code sinh k bằng `secrets.randbelow` (dùng CSPRNG của hệ điều hành) và không bao giờ dùng `random`.

### 10.3 Pool có giá trị như khóa bí mật

Ai biết một bộ (k, r) chưa dùng thì sẽ tính được x ngay khi bộ đó được dùng để ký. Vì vậy pool chỉ nằm trong RAM của tiến trình và không được ghi ra đĩa. Triển khai thật cần thêm:
- khóa vùng nhớ để pool không bị swap ra đĩa;
- xóa pool khi tiến trình fork hoặc khi máy ảo được khôi phục từ snapshot, vì snapshot sao chép cả pool và dẫn đến dùng lại k.

### 10.4 Không tương thích với RFC 6979

RFC 6979 sinh k một cách tất định từ khóa bí mật và H(m), nên không còn phụ thuộc vào chất lượng bộ sinh số ngẫu nhiên. Nhưng vì k phụ thuộc thông điệp, nó không thể tính trước. Đây là đánh đổi cốt lõi của đề tài. Một hướng lai là sinh `k = PRF(khóa bí mật, bộ đếm)`: vẫn tính trước được, mà không phụ thuộc RNG lúc chạy.

### 10.5 Kênh kề (side-channel)

Bảng fixed-base được tra theo các chữ số của k, nên địa chỉ truy cập bộ nhớ đệm có thể làm lộ k. Cài đặt an toàn phải tra bảng theo kiểu constant-time (đọc mọi phần tử rồi chọn bằng mặt nạ). Python không bảo đảm constant-time cho phép toán số lớn, nên dự án này chỉ đánh giá hiệu năng.

### 10.6 Tình trạng chuẩn

Theo [FIPS 186-5](https://doi.org/10.6028/NIST.FIPS.186-5), DSA chỉ được giữ lại để xác minh chữ ký đã có, không tạo chữ ký mới. Ý tưởng bảng fixed-base có thể chuyển sang phép nhân điểm của ECDSA/Schnorr, nhưng pool nonce cần thiết kế riêng theo lược đồ. ECDSA tất định theo [RFC 6979, mục 3.2](https://www.rfc-editor.org/rfc/rfc6979.html#section-3.2) và EdDSA theo [RFC 8032, mục 5.1.6](https://www.rfc-editor.org/rfc/rfc8032.html#section-5.1.6) sinh nonce từ thông điệp, nên không thể chuẩn bị nguyên xi pool nonce độc lập thông điệp như trong repo. Schnorr/EdDSA cũng không dùng công thức nghịch đảo nonce như DSA.

---

## 11. Demo, `main.py`, Docker

### `demo/demo_cli.py`

Tham số: `--level 2048|3072` và `--msg "nội dung"`. Các bước:

1. Nạp khóa và in mức bảo mật.
2. Phần offline: dựng bảng window và comb, lấp hai pool (V1, V4) mỗi pool 200 bộ, in thời gian và dung lượng bảng.
3. Ký cùng một thông điệp bằng V0, V2, V3, V1, V4 (mỗi biến thể 20 lần, lấy trung bình), R0 (3 lần) và R1 (5 lần). In thời gian, hệ số so với V0 và kết quả xác minh.
4. In chữ ký DSA (rút gọn) cùng kích thước của chữ ký DSA và RSA.
5. Sửa thông điệp thêm một ký tự và cho thấy xác minh trả về `False`.

Hàm `timed(fn, n)` chạy `fn` n lần và trả về kết quả cùng thời gian trung bình tính bằng µs. Số liệu của demo là để minh họa; số liệu chính thức là của benchmark.

### `main.py`

Ánh xạ mỗi lệnh sang một module và chạy module đó bằng `subprocess`. Lệnh `all` chạy lần lượt test → demo → bench → plots và dừng ngay nếu một bước lỗi. Các tham số đứng sau tên lệnh được chuyển tiếp nguyên vẹn, ví dụ `main.py bench e1` hay `main.py demo --level 3072`.

### `Dockerfile`

Dùng image `python:3.12-slim`, cài `requirements.txt`, chép toàn bộ code vào, `ENTRYPOINT` là `main.py` và lệnh mặc định là `demo`.

---

## 12. Tra cứu nhanh từng hàm

| File | Tên | Vai trò |
| --- | --- | --- |
| `core/modarith.py` | `modexp(base, exp, mod)` | lũy thừa modulo square-and-multiply |
| | `egcd(a, b)` | Euclid mở rộng: (g, x, y) |
| | `modinv(a, m)` | nghịch đảo modulo |
| | `batch_inv(values, m)` | nghịch đảo hàng loạt (Montgomery trick) |
| `core/primes.py` | `SMALL_PRIMES` | các số nguyên tố lẻ dưới 2000, dùng để sàng nhanh |
| | `is_probable_prime(n, rounds)` | Miller–Rabin |
| | `random_prime(bits)` | sinh số nguyên tố dài đúng `bits` bit |
| | `gen_dsa_params(L, N)` | sinh (p, q, g) |
| | `gen_rsa_key(bits, e)` | sinh (n, e, d, p, q) |
| `core/keystore.py` | `LEVELS` | hai mức (L, N) |
| | `generate(path)` | sinh và ghi `params.json` |
| | `load(path)` | đọc `params.json`, trả về khóa DSA, khóa RSA, thời gian sinh |
| `dsa/dsa.py` | `DSAParams`, `DSAKey` | dữ liệu tham số và khóa |
| | `keygen(params, expfn)` | sinh (x, y) |
| | `hash_to_int(msg, N)` | z = N bit trái nhất của SHA-256 |
| | `verify(key, msg, sig, expfn)` | xác minh DSA |
| | `_finish(key, msg, k_inv, r)` | tính s, dùng chung cho mọi biến thể |
| | `Signer` | lớp cha: `sign()` gọi `fresh_triple()` rồi `_finish()` |
| | `BaselineSigner` | V0 |
| | `FixedBaseSigner` | V2 (window) và V3 (comb) |
| | `PoolSigner` | V1 và V4, kèm fallback và bộ đếm `fallbacks` |
| `dsa/pool.py` | `PrecomputePool` | `fill`, `take`, `_make_batch`, `start_background`, `stop_background` |
| `dsa/fixed_base.py` | `_elem_bytes(x)` | số byte của một phần tử bảng |
| | `FixedBaseWindow` | bảng T[i][j], `pow(k)`, `entries`, `table_bytes` |
| | `CombLimLee` | bảng G[u], `pow(k)`, `entries`, `table_bytes` |
| `rsa/rsa.py` | `SHA256_PREFIX` | DigestInfo của SHA-256 theo RFC 8017 |
| | `RSAKey` | khóa, kèm dp, dq, qinv, k |
| | `emsa_pkcs1_v15(msg, k)` | đệm PKCS#1 v1.5 |
| | `sign(key, msg, crt, expfn)` | R0 (`crt=False`) hoặc R1 (`crt=True`) |
| | `verify(key, msg, sig, expfn)` | xác minh RSA |
| `bench/harness.py` | `measure`, `write_csv`, `env_info` | đo, ghi CSV, ghi thông tin máy |
| `bench/run_all.py` | `e1` … `e5`, `checked`, `verify_all`, `msgs` | các thí nghiệm và kiểm tra chữ ký trong lúc đo |
| `bench/plots.py` | `e1` … `e5`, `rows`, `short` | vẽ biểu đồ |
| `demo/demo_cli.py` | `main`, `timed` | demo |
| `main.py` | `COMMANDS`, `main` | lệnh chạy chung |

---

## 13. Tài liệu tham khảo

1. NIST FIPS 186-4 (2013) và FIPS 186-5 (2023), *Digital Signature Standard (DSS)*.
2. NIST SP 800-57 Part 1 Rev. 5 (2020), *Recommendation for Key Management* — bảng mức bảo mật tương đương.
3. K. Moriarty và cộng sự, RFC 8017 (2016), *PKCS #1: RSA Cryptography Specifications v2.2*.
4. T. Pornin, RFC 6979 (2013), *Deterministic Usage of DSA and ECDSA*.
5. C. H. Lim, P. J. Lee, *More Flexible Exponentiation with Precomputation*, CRYPTO 1994.
6. E. Brickell, D. Gordon, K. McCurley, D. Wilson, *Fast Exponentiation with Precomputation*, EUROCRYPT 1992.
7. A. Menezes, P. van Oorschot, S. Vanstone, *Handbook of Applied Cryptography*, CRC Press 1996, chương 4, 11 và 14.
8. N. Howgrave-Graham, N. Smart, *Lattice Attacks on Digital Signature Schemes*, Designs, Codes and Cryptography, 2001.
9. fail0verflow, *Console Hacking 2010: PS3 Epic Fail*, 27C3, 2010.

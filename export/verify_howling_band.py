"""verify_howling_band.py — 独立复算: 啸叫检测器对 band_k 激励是否系统性误判.

不读任何文档结论, 直接按 src/howling_detect.c 的算式重实现 detect_frame(),
喂真实 band_k.wav, 对比**旧检测带**(bin 2..24, 无边界保护)与**新检测带**
(bin 8..24 + HW_EDGE_GUARD), 看 anti 通道的 峰/均值比 分布会不会越过
HW_ANTI_THRESH_DB=12.

2026-09-14: 旧参数下 band_0 99.5% 帧、band_1 92.7% 帧越阈, 峰恒在最低 bin
(125Hz), 陷波器随之插在 125Hz —— 而它的 -3dB 阻带是 20-229Hz, 正砍在对消
目标带上. 真机实测该误插让 anti 掉 7.1dB、降噪量从 3.53dB 掉到 1.91dB.
本脚本用同一套算式复核: 新参数下 7 个 band 都不该再越阈.
"""
import numpy as np
import soundfile as sf

FS         = 16000
HW_FFT_N   = 256
THRESH_ERR  = 14.0
THRESH_ANTI = 12.0
HW_NOTCH_R  = 0.96
HW_ANTI_MIN_RMS2 = 4e-4

# (最低bin, 最高bin, 边界保护) —— 旧=故障参数, 新=当前参数
PARAMS = [
    ("旧 (bin 2..24, 无边界保护)", 2, 24, 0),
    ("新 (bin 8..24, guard=2)   ", 8, 24, 2),
]


def apply_hanning(buf):
    N = len(buf)
    i = np.arange(N)
    return buf * (0.5 * (1.0 - np.cos(2.0 * np.pi * i / (N - 1))))


def dft_power(buf, k):
    """与 C 版同式: 单频点 DFT, 未做 FFT 归一化 (只用于峰/均值比, 归一化抵消)."""
    n = np.arange(len(buf))
    theta = -2.0 * np.pi * k * n / len(buf)
    re = np.sum(buf * np.cos(theta))
    im = np.sum(buf * np.sin(theta))
    return re * re + im * im


def detect_frame(frame, thresh_db, kmin, kmax, guard):
    """对应 C 的 detect_frame(). 返回 (peak_db, 触发频率或 None, 是否被边界拦下)."""
    p = np.array([dft_power(frame, k) for k in range(kmin, kmax + 1)])
    mean_pwr = p.mean()
    if mean_pwr < 1e-12:
        return None
    peak_bin = kmin + int(np.argmax(p))
    peak_db = 10.0 * np.log10(p.max() / mean_pwr)
    freq = peak_bin * FS / HW_FFT_N

    if peak_bin - kmin < guard or kmax - peak_bin < guard:
        return peak_db, None, True          # 贴带边 → 判为带边, 不是谐振
    if peak_db > thresh_db:
        return peak_db, freq, False
    return peak_db, None, False


def scan(path, label, kmin, kmax, guard):
    d, fs = sf.read(path)
    assert fs == FS, fs
    d = np.asarray(d, dtype=np.float64)
    rms = float(np.sqrt((d ** 2).mean()))
    frames = len(d) // HW_FFT_N
    peaks, hits, freqs, edged = [], 0, [], 0
    for i in range(frames):
        fr = apply_hanning(d[i * HW_FFT_N:(i + 1) * HW_FFT_N].copy())
        r = detect_frame(fr, THRESH_ANTI, kmin, kmax, guard)
        if r is None:
            continue
        peaks.append(r[0])
        if r[2]:
            edged += 1
        if r[1] is not None:
            hits += 1
            freqs.append(r[1])
    peaks = np.array(peaks)
    gate_ok = (rms ** 2) > HW_ANTI_MIN_RMS2
    top = ""
    if freqs:
        vals, cnts = np.unique(np.round(freqs).astype(int), return_counts=True)
        top = "  触发频率: " + ", ".join(
            f"{v}Hz×{c}" for c, v in sorted(zip(cnts, vals), reverse=True)[:3])
    print(f"    {label}  中位 {np.median(peaks):5.1f}dB  "
          f"95% {np.percentile(peaks,95):5.1f}dB  越阈 {hits:4d}/{frames} "
          f"= {100*hits/frames:5.1f}%  带边拦下 {100*edged/frames:5.1f}%{top}")
    return hits / frames


print("=" * 100)
print("第 1 部分: 误判验证 —— detect_frame 在真实 band_k.wav 上的峰/均值比 (anti 阈值 12dB)")
print("=" * 100)

for name, kmin, kmax, guard in PARAMS:
    print(f"\n>>> {name}")
    for k in range(7):
        scan(f"data/synth_noise/band_{k}.wav", f"band_{k}", kmin, kmax, guard)

rng = np.random.default_rng(0)
wn = rng.normal(0, 0.05, 480000)
frames = len(wn) // HW_FFT_N
print(f"\n>>> 白噪对照 (等带宽, 宽带激励的正常表现)")
for name, kmin, kmax, guard in PARAMS:
    peaks = []
    for i in range(frames):
        fr = apply_hanning(wn[i * HW_FFT_N:(i + 1) * HW_FFT_N].copy())
        r = detect_frame(fr, THRESH_ANTI, kmin, kmax, guard)
        if r is not None:
            peaks.append(r[0])
    peaks = np.array(peaks)
    print(f"    {name}  中位 {np.median(peaks):.1f}dB  "
          f"95% {np.percentile(peaks,95):.1f}dB  最大 {peaks.max():.1f}dB")


print()
print("=" * 100)
print("第 2 部分: 陷波器落点 —— 修好之后它还能不能碰到 50-500Hz 对消目标带")
print("=" * 100)
w = np.arange(20, 1601, 1.0)
z = np.exp(-1j * 2.0 * np.pi * w / FS)


def notch_db(f0):
    b1 = -2.0 * np.cos(2.0 * np.pi * f0 / FS)
    a1 = -2.0 * HW_NOTCH_R * np.cos(2.0 * np.pi * f0 / FS)
    a2 = HW_NOTCH_R ** 2
    H = (1 + b1 * z ** -1 + z ** -2) / (1 + a1 * z ** -1 + a2 * z ** -2)
    return b1, a1, a2, 20 * np.log10(np.abs(H) + 1e-12)


for f0, note in ((125.0, "旧故障点 (峰被钉在最低 bin)"),
                 (625.0, "新参数下最低可插位置 (bin 10)")):
    b1, a1, a2, mag = notch_db(f0)
    below = w[mag <= -3.0]
    print(f"\n  陷波点 {f0:.0f}Hz  ({note})")
    print(f"    系数 b=[1, {b1:.4f}, 1] a=[1, {a1:.4f}, {a2:.4f}]")
    if len(below):
        print(f"    -3dB 阻带: {below.min():.0f} - {below.max():.0f} Hz "
              f"(宽 {below.max()-below.min():.0f} Hz)")
    for lo, hi, tag in ((50, 81, "band_0"), (81, 132, "band_1"),
                        (132, 215, "band_2"), (215, 349, "band_3"),
                        (349, 568, "band_4")):
        m = (w >= lo) & (w <= hi)
        print(f"    对 {tag} ({lo}-{hi}Hz) 平均衰减: {mag[m].mean():7.2f} dB")

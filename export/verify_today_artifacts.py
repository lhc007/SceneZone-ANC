"""verify_today_artifacts.py — 取证: 今天的 A/B 库到底装的是哪个 Wc.

疑虑: make_ab_bank.py 默认 --src data/wc_bank.bin, 而 CHANGELOG 记 wc_bank.bin
的槽 0 今天被两次失败标定覆盖 (中间态, 未还原). 若 13:37 建的 wc_bank_ab_slot0.bin
取的是被衰减过的"尸体" Wc, 那 A/B 比的是"垃圾 vs 零", ch1 当然不动 —— 与物理无关.

本脚本不说结论, 只把每个文件的每个槽算出来: ‖w‖ / max|w| / 峰值频率.
"""
import struct
import sys
from pathlib import Path

import numpy as np

root = Path(__file__).resolve().parent.parent
HDR_LEN = 16
FS = 16000


def load(path):
    raw = Path(path).read_bytes()
    magic, version, n_slots, slot_len = struct.unpack('<IIII', raw[:HDR_LEN])
    if magic != 0x434E4647:
        return None
    body = np.frombuffer(raw[HDR_LEN:HDR_LEN + n_slots * slot_len * 4], dtype='<f4')
    return body.reshape(n_slots, slot_len), n_slots, slot_len


def slot_stats(w):
    """w = float[2048] = S(2) × L(1024): 两个扬声器各 1024 tap"""
    n = len(w) // 2
    out = []
    for s in range(2):
        seg = w[s * n:(s + 1) * n]
        # 1024 点实 FFT
        X = np.fft.rfft(seg, n=4096)
        f = np.fft.rfftfreq(4096, 1.0 / FS)
        mag = np.abs(X)
        band = (f >= 20) & (f <= 1600)
        k = np.argmax(mag[band])
        peak_f = f[band][k]
        rms_in = np.sqrt(np.mean(mag[band] ** 2))
        out.append((np.linalg.norm(seg), np.max(np.abs(seg)),
                    peak_f, mag[band][k] / (rms_in + 1e-12)))
    return out


FILES = [
    ('HEAD (cb907cc) wc_bank.bin', None),
    ('工作区 data/wc_bank.bin', root / 'data/wc_bank.bin'),
    ('备份 .bak_20260914_pre_recal', root / 'data/wc_bank.bin.bak_20260914_pre_recal'),
    ('备份 .bak_20260912_step1', root / 'data/wc_bank.bin.bak_20260912_step1'),
    ('A/B 库 wc_bank_ab_slot0.bin', root / 'data/wc_bank_ab_slot0.bin'),
    ('A/B 库 wc_bank_ab_slot3.bin', root / 'data/wc_bank_ab_slot3.bin'),
    ('增益扫描 wc_bank_gain_slot0.bin', root / 'data/wc_bank_gain_slot0.bin'),
    ('wc_bank_zero.bin', root / 'data/wc_bank_zero.bin'),
    ('wc_bank_scratch.bin', root / 'data/wc_bank_scratch.bin'),
]

print('=' * 96)
print('每个库文件的 7 个槽: ‖w‖ (两通道), 峰值频率, 峰/带内RMS')
print('=' * 96)
print(f"{'文件':<34} {'槽':>3} {'‖w‖_spk0':>10} {'‖w‖_spk1':>10} {'峰spk0':>8} {'峰spk1':>8} {'峰/RMS s0':>10}")

for label, path in FILES:
    if path is None:
        import subprocess
        raw = subprocess.run(['git', 'show', 'HEAD:data/wc_bank.bin'],
                             cwd=root, capture_output=True).stdout
        magic, version, n_slots, slot_len = struct.unpack('<IIII', raw[:HDR_LEN])
        body = np.frombuffer(raw[HDR_LEN:HDR_LEN + n_slots * slot_len * 4], dtype='<f4')
        arr = body.reshape(n_slots, slot_len)
    else:
        if not path.exists():
            print(f'{label:<34}  (缺失)')
            continue
        r = load(path)
        if r is None:
            print(f'{label:<34}  (魔数不对)')
            continue
        arr, n_slots, slot_len = r

    for c in range(arr.shape[0]):
        st = slot_stats(arr[c])
        print(f'{label if c == 0 else "":<34} {c:>3} '
              f'{st[0][0]:>10.4f} {st[1][0]:>10.4f} '
              f'{st[0][2]:>7.0f}Hz {st[1][2]:>7.0f}Hz {st[0][3]:>10.2f}')
    print('-' * 96)

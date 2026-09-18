"""make_gain_bank.py — 造「增益扫描」库: 每个槽放同一份 Wc 的不同倍数.

为什么需要:
  实测 (2026-09-14 同时段 A/B): anti 在 0.0002 ↔ 0.115 之间来回切, 误差麦 ch1 只动
  不到 1dB。即"无论 Wc 是什么, 误差麦都不动"。病因只剩两种可能, 治法完全相反:

    (a) anti 传到误差麦的贡献 **远小于** ch1  → 次级路径太弱, ANC 物理上没劲
    (b) anti 传到误差麦的贡献 **≈ ch1**       → 相位/延迟不对

  直接测灵敏度就能分开: 把 Wc 整体乘 k 倍, anti 就跟着变 k 倍。看 ch1 有没有反应。

    k 从 0.25 扫到 2.0 (18dB 动态范围) 而 ch1 纹丝不动 → (a), 别再调软件了
    ch1 明显跟着 k 走, 且在某个 k 取最小             → (b), 而且那个 k 就是绝对增益误差

  槽里故意放 3 个重复的 1.0×, 用来量**同一段运行内**的重复性 —— 判任何差异前先看它。

用法:
  python export/make_gain_bank.py --slot 0
      → data/wc_bank_gain_slot0.bin

配套运行 (必须 fixed 模式):
  $env:GFANC_ANC_MODE="fixed"; $env:GFANC_MIC_GAIN="1.0"
  $env:GFANC_BANK_FILE="data/wc_bank_gain_slot0.bin"
  $env:GFANC_BANK_SIM="1"; $env:GFANC_BANK_SIM_SEC="8"
  .\\scenezone_realtime.exe

  日志 "[BANK] class a → b (slot b ... SIM)" 的 slot 号对着下面的表看增益。
  ⚠ SIM_SEC 用 8 而不是 4: anti/ch 都是**1秒平均**, 4秒窗口里只有一半可用。
    8秒窗口能拿到 ~7 个干净样本/槽。

注意: 输出是**另建文件**, 不动 data/wc_bank.bin。
"""
import argparse
import hashlib
import struct
from pathlib import Path

import numpy as np

script_dir = Path(__file__).resolve().parent
root = script_dir.parent
HDR_LEN = 16

# 槽 → (增益, 说明)。3 个 1.0× 是运行内重复性对照, 0.0× 是真正的 ANC 关。
GAINS = [
    (1.00, '参考 (标定解原样)'),
    (0.50, '半幅'),
    (1.00, '参考 — 重复1 (量运行内重复性)'),
    (2.00, '两倍  ⚠ 注意 anti 是否触削波'),
    (0.25, '四分之一'),
    (1.00, '参考 — 重复2 (量运行内重复性)'),
    (0.00, 'ANC 关 (绝对基准)'),
]


def main():
    ap = argparse.ArgumentParser(description='造增益扫描库')
    ap.add_argument('--slot', type=int, required=True, help='被测槽号 k (0..6)')
    ap.add_argument('--src', default=str(root / 'data' / 'wc_bank.bin'))
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    src = Path(args.src)
    raw = src.read_bytes()
    magic, version, n_slots, slot_len = struct.unpack('<IIII', raw[:HDR_LEN])
    if magic != 0x434E4647:
        raise SystemExit(f'ERROR: {src} 魔数不对: 0x{magic:08X}')
    if not (0 <= args.slot < n_slots):
        raise SystemExit(f'ERROR: --slot {args.slot} 超范围 (库有 {n_slots} 槽)')
    if len(GAINS) != n_slots:
        raise SystemExit(f'ERROR: GAINS 有 {len(GAINS)} 条, 库有 {n_slots} 槽 — 不一致')

    slot_bytes = slot_len * 4
    body = raw[HDR_LEN:]
    if len(body) != n_slots * slot_bytes:
        raise SystemExit(f'ERROR: 库体 {len(body)} 字节 != {n_slots}×{slot_bytes}')

    wc = np.frombuffer(body[args.slot * slot_bytes:(args.slot + 1) * slot_bytes],
                       dtype='<f4').astype(np.float64)
    if not np.all(np.isfinite(wc)):
        raise SystemExit(f'ERROR: 槽 {args.slot} 含非有限值')

    out = bytearray(raw[:HDR_LEN])
    print('=' * 68)
    print(f'  增益扫描库 → slot {args.slot}  ‖w‖ = {np.linalg.norm(wc):.4f}')
    print(f'  源: {src}  (md5 {hashlib.md5(raw).hexdigest()})')
    print('-' * 68)
    for c, (g, note) in enumerate(GAINS):
        scaled = (wc * g).astype('<f4')
        out += scaled.tobytes()
        print(f'    槽 {c}: ×{g:<5.2f}  ‖w‖={np.linalg.norm(scaled):7.4f}   {note}')
    print('-' * 68)

    dst = Path(args.out) if args.out else root / 'data' / f'wc_bank_gain_slot{args.slot}.bin'
    dst.write_bytes(bytes(out))
    print(f'  跑法: GFANC_ANC_MODE=fixed  GFANC_BANK_FILE={dst.name}')
    print(f'        GFANC_BANK_SIM=1  GFANC_BANK_SIM_SEC=8')
    print(f'  {dst.name} md5 {hashlib.md5(bytes(out)).hexdigest()}')
    print('=' * 68)


if __name__ == '__main__':
    main()

"""make_ab_bank.py — 造一个「同时段 A/B」用的库: 偶数槽=被测解, 奇数槽=全零.

为什么需要:
  本机误差麦 ch1 在**单次运行内**就能漂 6dB (参考麦完全不动), 跨运行还有 2.6dB。
  任何靠"跑两次比一比"的结论, 只要小于这个漂移就分不出来 —— 而我们要量的是
  1~3dB 量级的降噪量。

  解法: 用 GFANC_BANK_SIM 让程序**每 N 秒自动换槽**。槽序号交替指向
  「被测 Wc」和「全零 Wc」, 于是同一段连续时间里 ANC 一直在开/关之间来回切。
  漂移同时作用在开和关两边, 相减就消掉了 —— 这才是严格同时段的 A/B。

用法:
  python export/make_ab_bank.py --slot 0
      → data/wc_bank_ab_slot0.bin
  python export/make_ab_bank.py --slot 3 --src data/wc_bank.bin

配套运行 (必须 fixed 模式):
  $env:GFANC_ANC_MODE="fixed"
  $env:GFANC_MIC_GAIN="1.0"
  $env:GFANC_BANK_FILE="data/wc_bank_ab_slot0.bin"
  $env:GFANC_BANK_SIM="1"
  $env:GFANC_BANK_SIM_SEC="4"
  .\\scenezone_realtime.exe

  日志里 "[BANK] class a → b (slot b, fade N SIM)" 的 slot 号就是当前用的是哪一槽:
  偶数槽(0/2/4/6)= ANC 开, 奇数槽(1/3/5)= ANC 关。对着 ch1/ch2/ch3 看开关差。

注意: 输出是**另建文件**, 不动 data/wc_bank.bin。
"""
import argparse
import hashlib
import struct
from pathlib import Path

script_dir = Path(__file__).resolve().parent
root = script_dir.parent

HDR_LEN = 16


def main():
    ap = argparse.ArgumentParser(description='造 A/B 库 (偶槽=被测解, 奇槽=全零)')
    ap.add_argument('--slot', type=int, required=True, help='被测槽号 k (0..6)')
    ap.add_argument('--src', default=str(root / 'data' / 'wc_bank.bin'),
                    help='源库 (默认 data/wc_bank.bin)')
    ap.add_argument('--out', default=None, help='输出路径 (默认 data/wc_bank_ab_slot<k>.bin)')
    args = ap.parse_args()

    src = Path(args.src)
    raw = src.read_bytes()

    magic, version, n_slots, slot_len = struct.unpack('<IIII', raw[:HDR_LEN])
    if magic != 0x434E4647:
        raise SystemExit(f'ERROR: {src} 魔数不对: 0x{magic:08X} (期望 0x434E4647)')
    if not (0 <= args.slot < n_slots):
        raise SystemExit(f'ERROR: --slot {args.slot} 超范围 (库有 {n_slots} 槽)')

    slot_bytes = slot_len * 4
    body = raw[HDR_LEN:]
    if len(body) != n_slots * slot_bytes:
        raise SystemExit(f'ERROR: 库体 {len(body)} 字节 != {n_slots}×{slot_bytes}')

    wc = body[args.slot * slot_bytes:(args.slot + 1) * slot_bytes]
    zero = bytes(slot_bytes)

    out = bytearray(raw[:HDR_LEN])
    for c in range(n_slots):
        out += wc if (c % 2 == 0) else zero

    dst = Path(args.out) if args.out else root / 'data' / f'wc_bank_ab_slot{args.slot}.bin'
    dst.write_bytes(bytes(out))

    print('=' * 64)
    print(f'  A/B 库 → {dst}')
    print(f'  源: {src}  (md5 {hashlib.md5(raw).hexdigest()})')
    print(f'  槽 {args.slot} 取出 {slot_bytes} 字节, 复制到所有偶数槽')
    print('-' * 64)
    for c in range(n_slots):
        tag = f'ANC 开 (槽 {args.slot} 的系数)' if c % 2 == 0 else 'ANC 关 (全零)'
        print(f'    槽 {c}: {tag}')
    print('-' * 64)
    print(f'  跑法: GFANC_ANC_MODE=fixed  GFANC_BANK_FILE={dst.name}')
    print(f'        GFANC_BANK_SIM=1  GFANC_BANK_SIM_SEC=4')
    print(f'  {dst.name} md5 {hashlib.md5(bytes(out)).hexdigest()}')
    print('=' * 64)


if __name__ == '__main__':
    main()

"""regen_band_wavs.py — 只重生成代表性宽带 band_k.wav, 改时长用.

背景: generate_synthetic_noise.py 是全量重生 — 它会连带重新生成 cls_k/*.wav
(7 类 × 2000 段) 和 bank_labels_{train,valid}.csv. 由于 RNG 流是按顺序消耗的,
改了 --represent-sec 就会让后续所有训练样本的随机序列整体错位 → 训练集被换掉,
与已导出的 cnn_bank_*.bin 不再对应.

本脚本只做一件事: 按 data/synth_noise/synth_noise_info.json 里记录的频带,
重生成 band_0..band_{N-1}.wav 到指定时长. cls_k/ 与标签 CSV 原样不动.

生成参数 (带通阶数 / RMS 目标 / 采样率) 从 generate_synthetic_noise 导入,
保证与原始文件同分布; 频带从 json 读, 保证与 CNN 训练时的类定义一致.

用法:
  python export/regen_band_wavs.py --sec 30
      # 默认把现有 band_k.wav 备份为 band_k.wav.bak<原时长>s, 再写入新的
  python export/regen_band_wavs.py --sec 30 --no-backup
"""
import os
import sys
import json
import argparse
import wave
from pathlib import Path

import numpy as np
import scipy.io.wavfile as wavfile

script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
root = script_dir.parent
sys.path.insert(0, str(script_dir))

from generate_synthetic_noise import FS, RMS_TARGET, bandpass_noise  # noqa: E402

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def wav_seconds(path):
    with wave.open(str(path), 'rb') as w:
        return w.getnframes() / float(w.getframerate())


def main():
    ap = argparse.ArgumentParser(description='只重生成 band_k.wav, 改时长用')
    ap.add_argument('--sec', type=float, default=30.0, help='新时长 (秒, 默认 30)')
    ap.add_argument('--seed', type=int, default=0, help='随机种子 (默认 0, 可复现)')
    ap.add_argument('--out-dir', default=None,
                    help='目录 (默认 <项目根>/data/synth_noise)')
    ap.add_argument('--no-backup', action='store_true',
                    help='不备份原文件 (默认会备份为 band_k.wav.bak<原时长>s)')
    args = ap.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else root / 'data' / 'synth_noise'
    info_path = out_dir / 'synth_noise_info.json'
    if not info_path.exists():
        raise SystemExit(f'ERROR: 找不到 {info_path}')
    with open(info_path, encoding='utf-8') as f:
        info = json.load(f)
    bands = info['bands_hz']
    N = info['n_classes']
    if len(bands) != N:
        raise SystemExit(f'ERROR: bands_hz 有 {len(bands)} 条, n_classes={N} — 不一致')

    print('=' * 64)
    print(f'  只重生成 band_k.wav  ({N} 个, → {args.sec:g}s)')
    print(f'  目录: {out_dir}')
    print(f'  参数: fs={FS}  RMS={RMS_TARGET}  seed={args.seed}  (沿用原生成参数)')
    print(f'  cls_k/ 与 bank_labels_*.csv 不动')
    print('=' * 64)

    rng = np.random.RandomState(args.seed)
    for k, (lo, hi) in enumerate(bands):
        path = out_dir / f'band_{k}.wav'
        old_sec = None
        if path.exists():
            old_sec = wav_seconds(path)
            if not args.no_backup:
                bak = out_dir / f'band_{k}.wav.bak{old_sec:g}s'
                if not bak.exists():
                    bak.write_bytes(path.read_bytes())
                    print(f'\n[类 {k}] 原文件 {old_sec:g}s → 备份 {bak.name}')
                else:
                    print(f'\n[类 {k}] 备份已存在, 跳过: {bak.name}')

        y = bandpass_noise(lo, hi, args.sec, rng)
        wavfile.write(str(path), FS, (y * 32767).astype(np.int16))

        rms = float(np.sqrt(np.mean(y ** 2)))
        peak = float(np.max(np.abs(y)))
        print(f'[类 {k}] [{lo:7.1f}, {hi:7.1f}] Hz → {path.name}  '
              f'{args.sec:g}s  RMS={rms:.4f}  peak={peak:.4f}  '
              f'crest={peak / rms:.2f}')

    print(f'\n  完成: {N} 个 band_k.wav 已更新为 {args.sec:g}s')
    print(f'  ⚠️  库槽的标定产物 (data/wc_bank.bin) 未受影响 — 需重新标定才与新媒体对应')


if __name__ == '__main__':
    main()

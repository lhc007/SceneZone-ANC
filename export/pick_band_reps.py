"""pick_band_reps.py — 从已有合成语料里自动挑 N 条频带分散的代表噪声（复刻 band_k.wav 角色）.

背景: generate_synthetic_noise.py 自产 band_0..N-1.wav（每类全频带宽带）喂 generate_bank.py
  --filters-dir 造库。若你已有合成语料（如 SFANC-Window 同源数据集，7.5 万条），不用重新
  生成样本——直接从语料里按频谱质心分 N 个对数频带，每带挑 1 条代表 clip，写成
  band_0..N-1.wav + synth_noise_info.json，使 --filters-dir 直接复用同一套下游命令。

注意: 挑出的是语料里"该频带的窄带 clip"，不是全带宽带；库槽语义 = 该 clip 的频带
  （MIMO-SFANC 同款: 随机噪声收敛即可, 槽由代表噪声定义）。频带划分与 gen_bandpass_fir
  对齐 50-1500Hz（--band-low/--band-high 可改, 改后要同步改 gen_bandpass_fir.py）。

用法:
  python export/pick_band_reps.py --wav-dir <语料目录> --n-reps 7
    → data/synth_noise/band_0..N-1.wav + data/synth_noise/synth_noise_info.json
  # 造库照常:  python export/generate_bank.py --filters-dir data/synth_noise -o data/wc_bank.bin
  # 打标:      python export/generate_bank.py --labels --wav-dir <语料> --max-files 20000 -o data/wc_bank.bin

重计算 (离线 FxLMS 造库 + 打分 + CNN 训练) 留给用户自己跑，本脚本只挑代表 + 写 wav.
"""
import os, sys, json, argparse
from pathlib import Path
import numpy as np
import torchaudio
from scipy.signal import stft
from scipy.io import wavfile

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

FS = 16000
BAND_LOW = 50.0     # 与 gen_bandpass_fir.py --f-low 50 对齐
BAND_HIGH = 1500.0  # 与 gen_bandpass_fir.py --f-high 1500 对齐
RMS_TARGET = 0.05   # 与生成器同 RMS 目标


def spectral_centroid(path):
    """读 1s 16k 单声道 → 频谱质心 (Hz)。返回 None 若太短/加载失败。"""
    try:
        sig, sr = torchaudio.load(path)
    except Exception:
        return None
    if sig.shape[0] > 1:
        sig = sig.mean(dim=0, keepdim=True)
    if sr != FS:
        sig = torchaudio.functional.resample(sig, sr, FS)
    x = sig.squeeze().cpu().numpy()
    if x.size < FS:
        return None
    f, t, Z = stft(x[:FS], FS, nperseg=512)
    p = np.abs(Z).mean(1)
    tot = p.sum()
    if tot < 1e-12:
        return None
    return float((p * f).sum() / tot)


def log_bands(n, lo, hi):
    """对数分频: N 个频带覆盖 [lo, hi] (与生成器 log_bands 同式)."""
    r = (hi / lo) ** (1.0 / n)
    return [(lo * r ** k, lo * r ** (k + 1)) for k in range(n)]


def main():
    ap = argparse.ArgumentParser(
        description='从已有合成语料挑 N 条频带分散的代表噪声 (复刻 band_k.wav)')
    ap.add_argument('--wav-dir', required=True, help='合成语料目录 (递归扫 *.wav)')
    ap.add_argument('--n-reps', type=int, default=7, help='代表噪声数 N (== 库槽数, 默认 7)')
    ap.add_argument('--band-low', type=float, default=BAND_LOW, help='整体频带下限 Hz')
    ap.add_argument('--band-high', type=float, default=BAND_HIGH, help='整体频带上限 Hz')
    ap.add_argument('--out-dir', default=None,
                    help='输出目录 (默认 <项目根>/data/synth_noise)')
    ap.add_argument('--max-files', type=int, default=3000,
                    help='抽样上限 (算频谱质心较快; 挑代表 3000 条足够)')
    ap.add_argument('--represent-sec', type=float, default=10.0,
                    help='每条代表时长 (秒, 循环该 clip; generate_bank 会再循环到 train_sec)')
    ap.add_argument('--seed', type=int, default=0)
    args = ap.parse_args()

    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    root = script_dir.parent
    out_dir = Path(args.out_dir) if args.out_dir else root / 'data' / 'synth_noise'
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(p for p in Path(args.wav_dir).rglob('*.wav'))
    if args.max_files:
        files = files[:args.max_files]
    if not files:
        raise SystemExit(f'ERROR: {args.wav_dir} 下无 *.wav')

    print('=' * 60)
    print(f'  从已有语料挑 {args.n_reps} 条频带分散代表 (复用合成语料)')
    print(f'  语料: {args.wav_dir}  (共扫 {len(files)} 条)')
    print('=' * 60)

    cents = []
    for i, p in enumerate(files):
        cents.append(spectral_centroid(str(p)))
        if (i + 1) % 500 == 0:
            print(f'  频谱质心 {i+1}/{len(files)}')
    valid = [i for i, c in enumerate(cents) if c is not None]
    if not valid:
        raise SystemExit('ERROR: 没有可用的 1s @16k wav')

    bands = log_bands(args.n_reps, args.band_low, args.band_high)
    c_arr = np.array([cents[i] for i in valid])

    picked = []   # (file_idx, lo, hi, centroid)
    for k, (lo, hi) in enumerate(bands):
        c_k = float(np.sqrt(lo * hi))
        in_band = [i for i in valid if lo <= cents[i] <= hi]
        if in_band:
            c_in = np.array([cents[i] for i in in_band])
            j = in_band[int(np.argmin(np.abs(c_in - c_k)))]
        else:
            # 该带没样本: 取全局质心最接近带中心的一条 (兜底, 仍能出满 N 槽)
            j = valid[int(np.argmin(np.abs(c_arr - c_k)))]
        picked.append((j, lo, hi, cents[j]))

    info = {
        'n_classes': args.n_reps, 'clips_per_class': None,
        'bands_hz': [list(map(float, b)) for b in bands],
        'band_low': args.band_low, 'band_high': args.band_high,
        'represent_sec': args.represent_sec,
        'fs': FS,
        'method': 'picked-from-corpus: spectral-centroid split into N log bands, '
                  'one representative clip per band (MIMO-SFANC style)',
        'source_wavs': [str(files[i]) for i, *_ in picked],
        'seed': args.seed,
    }
    info_path = out_dir / 'synth_noise_info.json'
    with open(info_path, 'w', encoding='utf-8') as f:
        json.dump(info, f, indent=2, ensure_ascii=False)

    for k, (i, lo, hi, c) in enumerate(picked):
        p = files[i]
        sig, sr = torchaudio.load(str(p))
        if sig.shape[0] > 1:
            sig = sig.mean(dim=0, keepdim=True)
        if sr != FS:
            sig = torchaudio.functional.resample(sig, sr, FS)
        x = sig.squeeze().cpu().numpy().astype(np.float32)
        n_want = int(args.represent_sec * FS)
        if x.size < n_want:
            x = np.tile(x, int(np.ceil(n_want / x.size)))[:n_want]
        else:
            x = x[:n_want]
        rms = np.sqrt(np.mean(x ** 2))
        if rms > 1e-12:
            x = x * (RMS_TARGET / rms)
        out = out_dir / f'band_{k}.wav'
        wavfile.write(str(out), FS, (x * 32767).astype(np.int16))
        print(f'  [槽 {k}] 频带 [{lo:.0f}, {hi:.0f}] Hz  ← {Path(p).name} (质心 {c:.0f} Hz)')

    print(f'\n  已写 {args.n_reps} 条代表 → {out_dir}/band_0..{args.n_reps-1}.wav + synth_noise_info.json')
    print('  下一步:')
    print(f'    python export/generate_bank.py --filters-dir {out_dir} -o data/wc_bank.bin')
    print(f'    python export/generate_bank.py --labels --wav-dir {args.wav_dir} --max-files 20000 -o data/wc_bank.bin')


if __name__ == '__main__':
    main()

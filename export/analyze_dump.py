#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GFANC_DUMP_REF 转储的谐波梯子分析 (2026-09-18).

用法:  python export/analyze_dump.py <前缀> [基频Hz]
  例:  python export/analyze_dump.py data/tone_test/dz 250

读 <前缀>.ref.wav / .err.wav / .anti.wav (16k 单声道 int16), 每路给两行:
  rel = 各次谐波相对基频的 dB (看失真形状)
  abs = 各次谐波的绝对 dBFS   (A/B 两次运行之间**唯一可比的量**)
三路的语义:
  ref  = 参考麦原始电平 (抗混叠后, 未过 mic 增益/AGC) = 房间实际有什么
  err  = 误差麦 ch1 原始电平
  anti = 实际送 DAC 的反噪 = ANC 喇叭被驱动的信号 (数字域)
判读 (A=零库/ANC 静音, B=真库/ANC 工作):
  * B.ref 的谐波高于 A.ref → ANC 喇叭在添失真; A≈B → 是放音设备
  * anti 自身有高次谐波 → 数字链路造的; 没有 → 是换能器/模拟侧
跳过前 2 秒 (INIT ramp / mute_hold), 末尾 0.5 秒也可能不完整, 一并丢掉.
不依赖 wave 模块 (容错: 文件短于头声明/奇数长度都按实际字节数读).
"""
import sys
import numpy as np

FS = 16000
NFFT = 16384          # 1.024s @16k
SKIP_SEC = 2.0
TAIL_SEC = 0.5
HARM_MAX = 5000.0     # 统计到 5kHz (抗混叠 fc≈6k, 之上无意义)


def load(path):
    """读 16k 单声道 int16 WAV 的数据体; 容错短文件/奇数尾巴."""
    raw = open(path, 'rb').read()
    if len(raw) <= 44:
        raise ValueError('文件太短 (%d 字节)' % len(raw))
    if raw[:4] != b'RIFF' or raw[8:12] != b'WAVE':
        raise ValueError('不是 WAV (头=%r)' % raw[:12])
    body = raw[44:]
    body = body[:len(body) // 2 * 2]        # 奇数尾巴丢掉 (不完整样本)
    return np.frombuffer(body, '<i2').astype(np.float64) / 32768.0


def welch(d):
    skip = int(SKIP_SEC * FS)
    end = len(d) - int(TAIL_SEC * FS)
    seg = d[skip:end] if end - skip >= NFFT else d[:len(d) // NFFT * NFFT]
    if len(seg) < NFFT:
        return None, None
    win = np.hanning(NFFT)
    acc = np.zeros(NFFT // 2 + 1)
    cnt = 0
    for i in range(0, len(seg) - NFFT + 1, NFFT // 2):
        acc += np.abs(np.fft.rfft(seg[i:i + NFFT] * win)) ** 2
        cnt += 1
    if cnt == 0:
        return None, None
    f = np.fft.rfftfreq(NFFT, 1.0 / FS)
    # 幅度: 窗的相干增益 = sum(win)/NFFT = 0.5 (Hann); 功率已按块平均
    return f, np.sqrt(acc / cnt) / (0.5 * NFFT / 2.0)


def amp_at(f, a, tgt, tol=15.0):
    m = (f > tgt - tol) & (f < tgt + tol)
    return a[m].max() if m.any() else 0.0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    prefix = sys.argv[1]
    f0 = float(sys.argv[2]) if len(sys.argv) > 2 else 250.0
    ks = [k for k in range(1, int(HARM_MAX / f0) + 1)]
    print('前缀 %s  基频 %.1fHz  谐波到 %d  跳过前 %.0fs/去尾 %.1fs  NFFT=%d'
          % (prefix, f0, ks[-1], SKIP_SEC, TAIL_SEC, NFFT))
    hdr1 = '%-5s %-4s %7s' % ('文件', '行', 'RMS')
    hdr2 = '%-5s %-4s %7s' % ('', '', '')
    for k in ks:
        hdr1 += ' %6s' % ('%dk' % k if k > 1 else 'f0')
        hdr2 += ' %6d' % round(k * f0)
    print(hdr1)
    print(hdr2)
    for tag in ('ref', 'err', 'anti'):
        try:
            d = load('%s.%s.wav' % (prefix, tag))
        except Exception as e:
            print('%-5s 读取失败: %s' % (tag, e))
            continue
        f, a = welch(d)
        if f is None:
            print('%-5s 数据不足 (%d 样本)' % (tag, len(d)))
            continue
        base = amp_at(f, a, f0)
        rel = ''; ab = ''
        for k in ks:
            v = amp_at(f, a, k * f0)
            rel += ' %6s' % ('---' if base <= 0 else '%.1f' % (20 * np.log10(v / base + 1e-12)))
            ab  += ' %6.1f' % (20 * np.log10(v + 1e-12))
        print('%-5s %-4s %7.4f%s' % (tag, 'rel', d.std(), rel))
        print('%-5s %-4s %7s%s' % ('', 'abs', 'dBFS', ab))
    print('\nrel = dB 相对基频    abs = 绝对 dBFS (A/B 两次运行之间比这一行)')
    return 0


if __name__ == '__main__':
    sys.exit(main())

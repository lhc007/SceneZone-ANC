/** howling_detect — DFT 频谱峰值检测 + IIR 陷波滤波器
 *
 * 原理: 啸叫是正反馈环路在特定频率自激产生的窄带单音.
 *       对误差信号做短时频谱分析, 检测持续存在的窄带峰值,
 *       确认后用 IIR 陷波器从输出中移除该频率分量.
 *
 * 用法:
 *   howling_detect_t hw;
 *   howling_init(&hw, 1, 1);  // enabled=跑检测, actuate=陷波是否下发到输出
 *                             // 标定期建议 (1, 0): 看得见谐振, 但不动输出
 *
 *   在音频回调中每样本调用:
 *     howling_tick(&hw, err_avg, anti_out);
 *   内部自动累积 256 样本 → DFT → 峰值检测 → 陷波 anti_out (actuate=0 时不下发)
 */
#ifndef HOWLING_DETECT_H
#define HOWLING_DETECT_H

#define HW_FFT_N        256      /* DFT 窗口 (16ms @ 16kHz, bin 间隔 62.5Hz) */
#define HW_MIN_BIN      8        /* 搜索带下限 bin (500Hz). 只是"搜哪", 不是"能插哪"
                                    —— 可落点被 HW_EDGE_GUARD 再收窄, 见下 */
#define HW_MAX_BIN      24       /* 搜索带上限 bin (~1500 Hz, 匹配带通上限) */

/* ── 检测带下限 2→8 (125Hz→500Hz), 2026-09-14 ──────────────────────────────
   旧值 2 (125Hz) 的病灶: 50-500Hz 是 ANC 的工作带, 而我们**故意**在里面注入
   窄带能量去对消. 该频段任何窄带激励在 62.5Hz 的 bin 分辨率下都"长得像单音"
   —— band_0 (50-81Hz) 整个带宽 31Hz, 还不到 1 个 bin. 于是:
     · 激励整段落在检测带以下时, 带内只剩带通裙边, 峰/均值比失去物理意义,
       且峰恒被钉在搜索带的最低 bin(125Hz);
     · 陷波器随即插在 125Hz, 而它的 -3dB 阻带是 20-229Hz —— 正砍在对消目标带上.
   实测 (export/verify_howling_band.py, 1875 帧/文件): band_0 99.5% 帧、
   band_1 92.7% 帧越过 anti 阈值 12dB; 误插后 band_0 平均 -6.98dB、band_1 -22.48dB.
   真机验证 (2026-09-14, 库槽0 66Hz 解, "偶数槽 vs 零槽"配对):
     陷波开 anti=0.1135 / 关 anti=0.2570 = 2.26x = 7.1dB
     (按陷波系数算出的 66Hz 衰减 = 6.80dB, 吻合)
     误差麦 ch1 降噪量 3.53dB → 1.91dB —— 陷波器吃掉约 41% 的降噪量.

   下限取 500Hz 的依据: 8 扬声器周边 42cm 间距 → 空间采样上限
   f_max = c/(2d) = 343/(2×0.42) ≈ 408Hz.
   低于此阵列本可产生相干对消场, 在此插陷波 = 自己拆自己的输出; 高于此阵列
   本就无法定向, 插陷波代价小.
   (原出处 docs/窗户ANC可行性-因果限制_实测_方案.md:181, 该文档已不在工作区.)

   ⚠ 搜索带 ≠ 陷波落点 (2026-09-18 澄清): 下面的 HW_EDGE_GUARD 会再砍掉贴边 2 个
   bin, 所以本检测器**实际能插陷波的范围是 bin 10..22 = [625, 1375]Hz**, 比
   HW_MIN_BIN 名义上的 500Hz 更窄. 方向是安全的 (更远离对消带), 但别按 500Hz 推理
   覆盖范围 —— 500-625Hz 这一段本检测器不保护.

   ⚠ 这是取舍: 625Hz 以下的环路啸叫不再由本检测器兜底. 现存兜底是电平/总量型的,
   按响应速度: 软限幅 |anti|≤~1.0 → peak_mute (|anti|>0.99 连续 10 样本≈0.6ms,
   adapt 下另把 Wc 减半) → safety_mute (err_rms>8×ref_rms, 1Hz) → P0-4 发散救援
   (err_ref 逐秒上升 ×2s → 回滚 last_good_wc) → max|Wc| freeze. 它们是宽带判据,
   不能像陷波器那样频率选择地掐单点, 且中等强度谐振要 2s 级才动. */
#define HW_EDGE_GUARD   2        /* 峰值须离搜索带边缘 ≥N bin, 否则是带边不是谐振.
                                    副作用: 有效陷波落点收窄为 bin 10..22 = [625, 1375]Hz */
/* P3: 阈值从 12/10 提高到 14/12 — 实测 125Hz 环境窄带(房间驻波/变压器)持续
   触发 9.7~12.8dB 峰均值比, 在旧阈值边界间歇激活释放陷波. 真正声学反馈啸叫
   峰均值比通常 >20dB, 14dB 仍有足够余量且可滤除多数环境伪峰.
   2026-09-14 注: 触发该问题的 125Hz 窄带现已在检测带外 (HW_MIN_BIN=8), 所以
   当初抬阈值的这条理由已不成立. 阈值本身未改 —— 调低会让陷波更激进, 没有
   证据支持, 留给后续单独决定. */
#define HW_THRESH_DB    14.0f    /* err通道 峰均值比阈值 */
#define HW_ANTI_THRESH_DB 12.0f  /* anti通道 峰均值比阈值 */
#define HW_ANTI_MIN_RMS2 4e-4f   /* anti帧功率下限 (RMS>0.02 才检测, 防静音期伪峰) */
#define HW_PERSIST       4       /* 连续帧数确认啸叫 (4帧≈64ms) */
#define HW_RELEASE       8       /* 啸叫消失后延迟释放帧数 */
#define HW_NOTCH_R       0.96f   /* 陷波器带宽 (越接近1越窄, 0.9-0.99) */
#define HW_MAX_NOTCHES   2       /* 最多同时陷波数 */
#define HW_MIN_HOLD      32      /* 陷波最小保持帧数 (32帧≈512ms, 防释放死循环) */
#define HW_S             2       /* 扬声器数 (每个扬声器独立 IIR 状态) */

typedef struct {
    int    enabled;              /* 1=跑 DFT 检测与状态机 (标定期也建议开, 只为观测) */
    int    actuate;              /* 1=把已确认的陷波下发到 anti_spk; 0=只检测不下发.
                                    标定期置 0: 落点 625-1375Hz 会砍 band_4/5/6, 与标定
                                    目标冲突 (旧 125Hz 误插砍掉 41% 降噪量是同一类错误).
                                    检测/计数/日志照常, 所以谐振有没有发生仍看得见. */

    /* DFT 累积缓冲 */
    float  buf[HW_FFT_N];
    float  abuf[HW_FFT_N];       /* anti 通道缓冲 (陷波前采样, 已陷波频率仍被持续监控) */
    int    buf_pos;

    /* 检测状态 */
    float  candidate_freq;      /* 候选啸叫频率 (Hz) */
    int    candidate_count;     /* 连续出现帧数 */
    float  active_freqs[HW_MAX_NOTCHES];  /* 已确认啸叫频率 */
    volatile int active_count;  /* 当前激活的陷波数 (回调写, 主线程读) */
    int    notch_age[HW_MAX_NOTCHES];  /* 每个陷波器的帧龄 (≥HW_MIN_HOLD才能释放) */
    int    release_timer;       /* 啸叫消失后延迟释放计时 */

    /* IIR 陷波器状态 (每扬声器 × 每频率独立, 避免跨通道串扰) */
    float  b1[HW_MAX_NOTCHES];  /* b0=1, b2=1 固定, 只需存 b1 */
    float  a1[HW_MAX_NOTCHES], a2[HW_MAX_NOTCHES];
    float  x1[HW_S][HW_MAX_NOTCHES], x2[HW_S][HW_MAX_NOTCHES];
    float  y1[HW_S][HW_MAX_NOTCHES], y2[HW_S][HW_MAX_NOTCHES];

    /* 监控 (err / anti 双通道, 2026-09-14 加 anti: 旧版只报 err, 而真正触发
       陷波的是 anti 通道 → 日志显示 peak=0.0dB "看起来没超" 却在插陷波,
       这个诊断盲区直接导致一次误判, 故两个通道都暴露出来) */
    volatile float dominant_freq;  /* err 通道最强候选频率 (Hz, 用于显示) */
    volatile float dominant_db;    /* err 通道最强候选峰均值比 (dB) */
    volatile float anti_freq;      /* anti 通道最强候选频率 (Hz) */
    volatile float anti_db;        /* anti 通道最强候选峰均值比 (dB) */
} howling_detect_t;

void howling_init(howling_detect_t *hw, int enabled, int actuate);

/** 每样本调用: 累积误差, 满一帧后 DFT 检测, 陷波 anti_spk (actuate=0 时只检测) */
void howling_tick(howling_detect_t *hw, float err_sample,
                  float *anti_spk, int S);

#endif

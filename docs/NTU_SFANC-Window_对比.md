# 与 NTU SFANC-Window 的对比记录

> **目的**: 记录本仓库方案与 NTU 2024 年 SFANC-Window 的异同，用于判断"为什么他们能到 10dB
> 左右而本仓库不能"。
>
> **证据纪律** (本文档强制):
> - **【代码】** = 可直接 grep 到的 `file:line`，可复核。**含 NTU 仓库代码**（2026-09-17 已取得）
> - **【实测】** = 本机跑出来的数字，附命令与文件
> - **【二手】** = 来自论文**摘要 / 检索摘要**，**未读到全文**
> - **【NTU-代码】** = 来自克隆下来的 NTU 仓库源码，可复核

> **仓库可达性（2026-09-17 更新）**: 用户开梯子后，**`codeload.github.com` 与
> `raw.githubusercontent.com` 可达**，`github.com` 直连仍不通。取仓库用:
> `curl -L -o sfanc.tgz https://codeload.github.com/Luo-Zhengding/SFANC-Window/tar.gz/refs/heads/main`
> **论文全文仍不可得**: Unpaywall 查 DOI `10.1016/j.ymssp.2024.111364` → `is_oa: False`，
> 无任何开放获取副本；sciencedirect 付费墙、dr.ntu.edu.sg 被 AWS WAF 拦。
> **→ 凡论文数字（含"10dB"）一律仍是【二手】，不可引用。**
> 该仓库**不含**滤波器训练代码，只含 CNN 与选槽逻辑。

日期: 2026-09-16（2026-09-17 依 NTU 仓库源码修订）
本仓库基线: `cb907cc` + 工作区未提交改动

---

## 1. 对比对象

- **论文**: Zhengding Luo, Dongyuan Shi, Junwei Ji, Xiaoyi Shen, Woon-Seng Gan.
  *Real-time implementation and explainable AI analysis of delayless CNN-based
  selective fixed-filter active noise control.*
  Mechanical Systems and Signal Processing, Vol. 214 (2024), 111364.
  DOI: `10.1016/j.ymssp.2024.111364`（2024-03-28 在线）
- **仓库**: <https://github.com/Luo-Zhengding/SFANC-Window>
- 同组相关工作: `SFANC-FxNLMS-ANC-Algorithm-based-on-Deep-Learning`、
  `Frequency-Direction-MCSFANC`（均未读）

---

## 2. 相同的部分 —— 思路确实一致

| 项 | NTU | 本仓库 |
|---|---|---|
| 采样率 | 16 kHz【NTU-代码】`Loading_real_wave_noise_2D.py:21`、`Acquired_sound.py:14` | 16 kHz（`FS_ANC`） |
| 控制滤波器长度 | 1024 tap【二手】（论文仿真段；**仓库未提**） | 1024 tap（`L=1024`） |
| 滤波器库槽数 | 7【NTU-代码】`Modified_ShufflenetV2(num_classes=7)` | 7（`wc_bank.bin`, slot_len=2048=2×1024） |
| 选槽机制 | 2D CNN（ShuffleNetV2 改）argmax【NTU-代码】`Control_filter_selection.py:51` | CNN（`cnn_m5`）argmax + 防抖 2 帧 |
| 部署形态 | 固定滤波器，无在线自适应【NTU-代码】notebook 只发 ID | `fixed` 开环，纯前向无梯度（`main_realtime.c:421`） |
| 切换抗爆音 | 未读到 | 1600 采样 delayless crossfade（`main_realtime.c:359-364`） |
| CNN 输入特征 | **Mel 谱** n_fft=1024/hop=512/n_mels=64 → power→dB，波形先 minmax 归一；张量 [1,64,32]【NTU-代码】`Loading_real_wave_noise_2D.py:29-52` | 参考麦带通后**线性谱**（自研特征） |
| 分类节奏 | **1 秒一帧**，帧间取**众数** `stats.mode(id_vector)`【NTU-代码】`Acquired_sound.py:33-58` | 每秒分类，防抖 2 帧 |
| 分类用哪个麦 | **笔记本自带/USB 麦，独占一路**（`input_device_index=1`），**不在 ANC 环内**【NTU-代码】`Acquired_sound.py:14-27` | **就是 ANC 参考麦**（同一路） |
| CNN 的环境相关性 | **环境无关**，换环境 CNN 不动（README 明写） | 同（CNN 也是离线训一次） |
| 滤波器索引 vs 类别 | **同一个数** —— 滤波器 k 就是类别 k | **两个独立变量**，见 3.7 |

**结论: 方案层面没有分歧，架构不是本仓库的问题所在。差别在实现细节与硬件条件。**

---

## 3. 不同的部分（按我判断的影响排序）

### 3.1 通道数 —— 4 次级源 vs 2 次级源

- **NTU【二手】**: 47cm × 47cm 的 4 通道 ANC 窗；1 参考麦 + **4 个次级声源** + **4 个误差麦**
- **本仓库【实测】**: 实时启动日志 `ANC ready: E=3 S=2 L=1024` → **2 个次级源**、3 个误差麦
- **判断**: 窗口这类大面积声场，"多点平均"的全局降噪量主要受**空间覆盖**限制，不是受单个
  滤波器性能限制。4 源铺满口径 vs 2 源，是结构性差异，且不是靠调参能补的。

### 3.2 滤波器是怎么来的 —— **两边其实是同一条路**（本节 2026-09-17 更正）

> **更正**: 此前这里写的是 "NTU【二手】: 离线用 FxLMS 仿真训到收敛"。读到 README 后
> 该表述**不成立**，见下。

- **NTU【NTU-代码/README】**: **滤波器训练代码不在仓库里**。README 原文:
  > "7 pre-trained control filters are **obtained in the 4-channel ANC window** with 1
  > reference microphone, 4 secondary sources, and 4 error sensors. **7 broadband noises
  > with different frequency ranges** are used as primary noises to obtain the
  > corresponding pre-trained control filters."
  > "To use the CNN-based SFANC method in new acoustic environments, **obtain the
  > corresponding pre-trained control filters in the new acoustic paths. The trained CNN
  > ... can remain unchanged.**"

  → 滤波器是**在目标环境（那个真实窗户）里、对着 7 个频段噪声逐个得到的**，
  换环境必须重新得到滤波器而 CNN 不动。**这与本仓库的真机标定是同一套做法。**
  （论文的 *仿真* 段用合成 pri/sec 路径，那是仿真验证，不是真机滤波器的来源。）
- **本仓库【代码】**: 真机在线跑，两条保存路径
- **本仓库【代码】**: 真机在线跑，两条保存路径
  - 自动: `check_wc_stable_autosave` —— Δ<5%/秒 连续 3 秒 且 RMS ≥ 3×初值
    （`main_realtime.c:911-913`、`955-974`）→ 存库并（`GFANC_CAL_EXIT=1` 时）退出
  - 兜底: `GFANC_CAL_SECS` 到点 → 走 Ctrl+C 路径存 `last_good_wc` 收敛快照
    （`main_realtime.c:1603-1611`、`1696-1699`）
- **真机标定要过的坎**（每一条都能在无人察觉时压低标定质量）:
  - 输出削顶后 `peak_mute` 反复减半 Wc（**adapt 模式下生效**；`fixed` 下由
    `!anc_fixed()` 守卫关闭，见 `main_realtime.c:527`）
  - 冷启动限幅 `cold_hold = 2*FS`，前 1 秒 cap=0.12（`main_realtime.c:1543`、`459`）
  - 啸叫检测、麦克风增益（`GFANC_MIC_GAIN` 必须逐槽钉死，否则槽间基准不一致）
- **判断（更正后）**: NTU 那几个坎**一个都躲不掉** —— 他们也是在真实窗户里跑自适应
  得到滤波器的。区别只在于: 他们的控制器是 **NI PXIe-8135 实时机**，I/O 确定性高、
  环路延迟低；本仓库是 Windows 笔记本 + USB 声卡，环路延迟 8.5–12.5ms（见 3.3），
  且上面那些约束（冷启动限幅、peak_mute、啸叫检测）都在同一条通路上。
  **所以"跑到任意收敛深度"不是本仓库相对 NTU 的劣势 —— 是两边都要面对的。**

### 3.3 环路延迟 —— delayless vs 实测 8.5–12.5ms

- **NTU【二手】**: 论文标题里的 "delayless" 就是核心卖点；实时控制器是 **NI PXIe-8135**
- **本仓库【实测】**: `data/sec_bulk_delay.bin` 历次测量值

  | 文件 | 值 | 折算 @16k |
  |---|---|---|
  | `sec_bulk_delay.bin`（当前） | 200 | 12.5 ms |
  | `sec_bulk_delay.bin.keep128` | 200 | 12.5 ms |
  | `sec_bulk_delay.bin.keep64` | 146 | 9.1 ms |
  | `sec_bulk_delay.bin.keep32` | 136 | 8.5 ms |

- **实时日志原文**:
  ```
  Loop delay auto-loaded: 200 (12ms), dsp_delay=190
  Ŝ model delay = 12.50ms (dsp_delay=190 + peak@10), 期望环路≈4-6ms
  ```
- **判断**: 代码自己写着期望 4–6ms，历次测量**从未落在该区间**。这是 Windows 笔记本 +
  USB 声卡 128 帧缓冲的固有代价，不是偶发测量错误。

### 3.4 部署模式的 NR 能不能测出来

- **NTU【二手】**: 有 4 个误差麦，NR 由误差麦测量并报告
- **本仓库【代码】**: `fixed` 模式把误差信号**强制清零**
  ```c
  /* main_realtime.c:381-386 */
  /* 方案C fixed 开环: 无误差麦 → err_meas 置 0. 梯度已被派发绕过,
     howling/NR 读到 0 无害; err_rms 显示 0 即"无误差麦"的诚实语义. */
  float err_meas[E];
  if (anc_fixed()) {
      for (int e = 0; e < E; e++) err_meas[e] = 0.0f;
  ```
  - 后果: `err_rms` 恒 0 → 报告行显示 `NR=n/a`；`antiEst` 也恒 0
  - **但误差麦的原始 RMS 仍在打印**（`raw: ch0(ref)=… ch1=… ch2=… ch3=…`，
    `main_realtime.c:779`），说明 3 个误差麦物理上是活的、有信号的
  - **连带后果**: `diverged`（`main_realtime.c:617`）与 `safety_mute`
    （`main_realtime.c:621`）都读 `err_rms`，在 `fixed` 下是**到不了的死代码**
- **判断**: NTU 有数可报，本仓库拿不到自己的部署 NR 数值。注意这条**不是纯显示改动** ——
  一旦让 `err_meas` 在 fixed 下不为零，`safety_mute` → `out_gain` 静音链会被激活，
  是**行为变更**。

### 3.5 离线与实时的延迟配置不一致 —— 影响此前**所有**离线结论

- **【代码】** `main.c:184`:
  ```c
  #define DSP_DELAY 0  /* 与实时版一致: Ŝ 已含声学延迟, 无硬件 I/O 延迟需补偿 */
  ```
- **【代码】** `main_realtime.c:1176`: 从 `data/sec_bulk_delay.bin` 自动加载 →
  `dsp_delay = 190`
- `sec_bulk_delay.bin` 只被 `main_realtime.c` 与 `src/calibrate_secondary.c` 引用，
  **`main.c` 从不读它**（grep 全仓可复核）
- **结论**: 离线仿真里**完全不存在**那 ~12ms 的 I/O 延迟，实时版有。`main.c:184` 那句
  "与实时版一致"**已经过时**。
- **影响**: 本仓库所有离线 dB 数字**偏乐观**，只能用于**槽间排序**，**不能当绝对值**。
  "仿真说 10dB、真机只有 3dB" 的差距，至少有一部分来自这里。

### 3.6 本仓库**原本就是** NTU 那条离线路线，后被真机标定覆盖

- **【代码】** `export/generate_bank.py` —— 就是 NTU 那套管线：
  N 段代表噪声 → 离线 FxLMS（经实测 Pri/Sec 路径）收敛 → N 条 1024-tap 滤波器 →
  写 `data/wc_bank.bin`（GFNC 16B 头，与 C 端 `src/scene_bank.c` 同格式）。
  脚本自称"与 SFANC-Window / MIMO-SFANC 同款，**无逐场景实机标定**"
- **【代码】** 参数与 NTU 对齐：`FS=16000`、`LEN_CTRL=1024`、`TRAIN_SEC=60`、MIMO
- **【代码】** 另有 `--labels` 模式：对每条 1s 噪声算 N 条候选滤波器的残差功率、
  取 argmin 当标签（MIMO-SFANC `generate_dataset_v2` 法）→ 训分类 CNN 用
- **【实测】** 依赖齐备：`SceneZone_Scene/Primary and Secondary Path/{primary,secondary}_path.npy`
  存在；`torch 2.12.0+cu126` 可用
- **【实测】** `data/wc_bank_info.json` 记录了产地：
  ```json
  "source_wavs": ["data\\synth_noise\\band_0.wav", ..., "data\\synth_noise\\band_6.wav"],
  "gain_scale": 1.0,
  "note": "离线 FxLMS 收敛成品 (绝对增益, 符号 = C 部署)"
  ```
  → **当前库最初就是离线生成的。**

**但**: 磁盘上的 `wc_bank.bin` 已被真机标定覆盖（槽 0 = 250Hz 纯音标定、槽 3 = 17:04
真机重标，其余槽字节未变，见 4.1）。所以
**`wc_bank_info.json` 的产地记录已与实际字节不符** —— 现在这个文件是
"离线生成 + 真机覆盖"的混合体。

**前置问题**: 见 4.2.1 的匹配槽悖论。离线重生成之前必须先分清
- ~~(a) 真机标定出来的 Wc 是坏的 → 离线路线即解药~~
- **(b)** 离线 Pri/Sec 模型与真机不同源 → 离线生成的滤波器在真机上同样不工作

**→ 4.2.3 的实测已推翻 (a)。** 离线库不比真机库好，且没有任何增益能救。

### 3.7 **滤波器索引 ≡ CNN 类别**（NTU 保证对齐，本仓库不保证）—— 2026-09-17 新增

这是目前找到的、**两边唯一一处结构性不同且能直接解释"NTU 有效 / 本仓库无效"的差异**。

- **NTU【NTU-代码/README】**: 7 个滤波器按**频段**编号 `b_0 … b_6`，CNN 输出 `num_classes=7`
  的 argmax，**这个整数直接就是滤波器编号**，通过 UDP 发给 PXIe
  （`Main_SFANC_Window.ipynb` → `UDP_sender.send_message(str(ID))`）。
  **索引和类别在编号上就是同一个数，不可能对不上。**
- **本仓库【代码】**: 两条独立链路
  - 标定写槽 = `cfg.cal_scene_index` = `GFANC_CAL_INDEX`，**默认 0**
    （`include/scenezone_types.h:180`；写库 `main_realtime.c:959`）
  - 部署读槽 = **CNN argmax**（`main_realtime.c:1504`）
  → 用 band_3 噪声标定但没设 `GFANC_CAL_INDEX=3`，成果就落在槽 0，
  而部署会去加载槽 3。**标定结果一次都不会被用到。**
  这正是 [[cal-index-vs-cnn-class-mismatch]] 记录的根因。
- **对当前状态的影响**: 槽 3 已用 `band_3.wav` 重标（4.1），**槽 3 这一对现在是对齐的**。
  所以**用 band_3 噪声测部署**才有意义 —— 250Hz 纯音会被 CNN 送到类 3，
  而纯音标定的成果在槽 0（4.3 已记），那种测法永远测不出东西。

### 3.8 纯 SFANC 的稳态误差 —— NTU 自己承认的局限【二手】

同组 SFANC-FxNLMS 混合算法论文（arXiv `2208.08082`）摘要原文:

> "The selective fixed-filter active noise control (SFANC) method ... **may lead to large
> steady-state errors due to inaccurate filter selection and the lack of adaptability.**"

即 **NTU 自己承认纯 SFANC 稳态误差大**，他们的改良方向是让 FxNLMS **继续在线更新**
被选中的那个预训练滤波器的系数。

**→ 对本仓库的含义**: `fixed` 开环纯回放是 SFANC 的最朴素形态，稳态误差大是**方法固有**的，
不是本仓库实现独有的 bug。若"10dB"确实存在，需查清它是不是来自纯 SFANC 那一段，
而不是混合算法那一段。

---

## 4. 本轮实测数据（供后续复核）

### 4.1 库现状（2026-09-16 17:04 写入后）

`data/wc_bank.bin`，7 槽，slot_len=2048

| 槽 | 目标频带 | 带内能量占比 | 峰值频点 | norm |
|---|---|---|---|---|
| 0 | 50–81 Hz | **1.4%** | 250.0 Hz | 0.8527 |
| 1 | 81–132 Hz | 86.1% | 132.8 Hz | 0.3535 |
| 2 | 132–215 Hz | 96.4% | 183.6 Hz | 0.5378 |
| 3 | 215–349 Hz | 96.0% | 236.3 Hz | 0.6517 |
| 4 | 349–568 Hz | 91.4% | 408.2 Hz | 0.6481 |
| 5 | 568–923 Hz | 97.9% | 748.0 Hz | 0.8313 |
| 6 | 923–1500 Hz | **60.8%** | 812.5 Hz | 0.4458 |

- **槽 0 是 250Hz 纯音标定的遗留物**（带内能量 1.4%），不是 band_0 解
- **槽 6 带内能量仅 60.8%**，未锁住自己的频带
- 槽 3 于 17:04 用 `band_3.wav` 写入（历次范数 0.81 → 0.72 → 0.65）
- 备份: `wc_bank.bin.bak_20260916_{155750,170119,170350}`

### 4.2 路噪离线逐槽（`main.exe`）

命令: `./main.exe "Noise Examples/road_noise-15.wav"`
（逐槽需临时移走 `data/cnn_bank_linear_weight.bin` 才走 `GFANC_FORCE_CLASS`）

**符号约定（已从代码核实）: `NR_true > 0 = 降噪`，`< 0 = 反相放大`**

```c
/* main.c:686-688 */
dis_pwr /= (len * E);
float nr_true = 10.0f * log10f((dis_pwr + 1e-12f) / (err_pwr / (len * E) + 1e-12f));
```
`dis_pwr` = 无 ANC 的扰动功率（Pri 模型），`err_pwr` = 有 ANC 的残差功率。
降噪时 err < dis → 比值 > 1 → **NR_true > 0**。

| 选槽方式 | 平均 NR_true | 读作 |
|---|---|---|
| 走 CNN 自动选槽（= 部署实际发生） | −4.7 dB | 放大 4.7 dB |
| 固定 slot 0 | −11.2 dB | 放大 11.2 dB |
| 固定 slot 1 | −6.4 dB | 放大 6.4 dB |
| 固定 slot 2 / 3 / 4 | −8.7 dB | 放大 8.7 dB |
| 固定 slot 5 | −7.5 dB | 放大 7.5 dB |
| 固定 slot 6 | **+3.0 dB** | **降噪 3.0 dB（唯一为正）** |

- 走 CNN 时 15 秒内跳槽 5 次: **0 → 6 → 1 → 6 → 5**
- 落在**类 6** 的秒 `NR_true` 为 **+2.4 ~ +3.1 dB**（这 4 秒是整段里**唯一在降噪**的）；
  落在类 0/1/5 的秒为 −5.8 ~ −11.3 dB（**在放大**）
- 该路噪频谱在 50–1500Hz 内分布很平: band1 24.5% / band5 17.3% / band6 15.3% /
  band0 14.4% / band2 10.8% / band4 10.2% / band3 7.5%
- ⚠ 见 3.5：这些数字**不含** 12ms I/O 延迟，偏乐观，只可用于排序
- ⚠ 残差 run-to-run 漂移约 2.6dB；slot 0 的 −11.2 与 slot 2/3/4 的 −8.7 只差 2.5dB，
  **在漂移量级内，不能当定论**

#### 4.2.1 匹配槽悖论 —— 离线表目前无法用来给库打分

用**匹配**输入 `data/synth_noise/band_3.wav.bak10s`（10s）逐个固定槽测：

| 固定槽 | NR_true | `err` 列（残差 RMS） | `anti` 列 | 备注 |
|---|---|---|---|---|
| slot 0（250Hz 纯音遗留解） | −17.5 | 8.2 | 0.110 | |
| **slot 3（band_3 匹配槽）** | **−14.1** | 5.4 | 0.085 | 匹配槽却仍是负的 |
| slot 6（近零输出） | **+2.3** | 0.82 | 0.005 | 几乎不注入 anti，落在基准附近 |

同一输入的 `dis_rms` 反推约 **1.08**（两次独立反推都是这个值，一致）。

**悖论**: 与输入匹配的 slot 3（−14.1，放大）反而**差于**几乎不输出的 slot 6（+2.3）。
一个基本不做事的滤波器不可能比匹配滤波器更好。

#### 4.2.2 已排除的解释（都做了实验）

**① 不是路径文件不同源** —— 逐值比对：
- `data/primary_path.bin` == `primary_path.npy[:,0,:]`，**max|diff|=0，corr=1.000000**
- `data/secondary_path.bin` == `secondary_path.npy`，**max|diff|=0，corr=1.000000**
→ 离线版与 `generate_bank.py` 用的是**同一次测量的同一份路径**。（注意 Pri 形状不同：
`.npy` 是 (3,2,1024) 双参考通道，`.bin` 是 (3,1,1024) 单通道 = 取了 npy 的第 0 通道。）

**② 不是延迟** —— 扫 `GFANC_VIRT_DELAY_MS`（band_3 输入，固定 slot 3）：

| 附加延迟 | 0ms | 4ms | 8ms | 11.9ms | 14ms | 16ms |
|---|---|---|---|---|---|---|
| NR_true | −14.1 | −14.0 | −14.0 | −13.6 | −14.7 | −13.8 |

**平的。** 延迟不是原因。（`GFANC_VIRT_DELAY_MS` 见 `main.c:302-307`。）

**③ 不是符号/polarity** —— 把槽 3 **整体取反**后重测：**−14.3**（原值 −14.1）。
取反几乎不改变结果 → 负 NR **不是"反相的对消信号"**，而是**不相干的过量注入**
（err_pwr ≈ dis_pwr + y_pwr，与 y 的符号无关）。这同时排除了
`generate_bank.py` 文档里那条"离线收敛后取反"的符号约定是主因。

**④ 是次级路径增益的世界不一致** —— `main.c:276-296`：

```c
/* 训练 (Disturbance_generation + FxNLMS_MIMO) 用原始 secondary_path 增益,
   若此处 peak→1.0 归一化 → Ŝ 整体缩小 (真实路径 ÷25.5) → anti 环路增益低 25.5 倍,
   Wc 必须膨胀才能抵消 pri → ... 发散 (road-15 根因).
   默认不归一化 (与训练一致); GFANC_SEC_NORM=1 恢复峰值归一化 (实时硬件标定兼容). */
```

即存在**两个"世界"**：

| 世界 | 次级路径增益 | 对应 |
|---|---|---|
| 离线训练世界 | 原始（peak≈34.5） | `generate_bank.py` + `main.exe` 默认 |
| 实时世界 | peak→1.0 | `scenezone_realtime.exe`（启动日志 `Ŝ: peak=34.4858 RMS=1.0000 → norm peak=1.00`） |

**实测**（band_3 输入，逐个固定槽，两个世界各跑一次）：

| 固定槽 | 默认（原始增益） | `GFANC_SEC_NORM=1`（实时兼容） |
|---|---|---|
| slot 0 | −17.5 | +1.3 |
| slot 3（匹配） | −14.1 | +0.7 |
| slot 6 | +2.3 | +0.7 |

- 默认世界：过度注入（−14 ~ −17）
- `SEC_NORM=1` 世界：**全部塌到 ≈0**（+0.7 ~ +1.3，即完全无效果）

**真机标定的 Wc 对原始增益的世界"太大"，对归一化的世界"太小" —— 离线 harness 的
两个设置**都**不能复现实时世界。**

**推论**: 4.2 那张逐槽表**不能用来判定库里哪个槽好**。`main.exe` 目前的
`GFANC_SEC_NORM` 两档都判不了真机标定的库。要判库，必须用**真机同时段 A/B**
（`export/make_ab_bank.py`）。

**这也直接卡住了"照 NTU 逻辑离线重建库"这条路**：离线重建会产出**离线世界**的
Wc，而实时 exe 活在**归一化世界**。两边的绝对增益缝没对上之前，重建出来的库
在真机上不会匹配 —— 这很可能正是当初从离线生成改用真机标定的原因。

#### 4.2.3 离线库 vs 真机库：直接对比（**结论：离线不更好**）

`git show HEAD:data/wc_bank.bin` 取出提交版 = **原始离线生成的那一份**
（`wc_bank_info.json` 记录的产地）。与当前版对比：槽 0–5 不同，**槽 6 完全相同**（从未重标）。

先确认对比公平：HEAD 版 slot 3 是**合格的 band-3 滤波器** —— 带内能量 **98.5%**、
峰值 **250.0Hz**。拿它测 band_3 输入是公平的。

**同一输入 `band_3.wav.bak10s`、同一 slot 3：**

| 库 | 默认（原始增益） | `SEC_NORM=1` |
|---|---|---|
| HEAD（离线生成） | **−13.0** | +1.1 |
| 当前（真机标定） | **−14.1** | +0.7 |

→ **离线版没有更好。** 两个世界档位都不工作。

**再扫整库增益**（HEAD 离线库，band_3 输入，slot 3）：

| gain | 0.2 | 0.3 | 0.5 | 0.7 | 1.0 | 1.5 | 2.0 | 3.0 | 5.0 |
|---|---|---|---|---|---|---|---|---|---|
| NR_true | −0.4 | −2.7 | −6.8 | −9.8 | −13.0 | −16.6 | −19.2 | −22.8 | −27.3 |

**单调下降，没有任何增益能转正。** 若只是"训练对了、幅度不对"，必存在某个增益
让 NR 明显为正。单调说明该滤波器在模型里的输出与扰动量**根本不相干**，
不是标量能修的。

**逻辑推论（比上面这些数字更要紧）**:
离线库是在**这个模型里**训练出来的。若 `main.exe` 的正向模型 == `generate_bank.py`
的训练模型，那离线训出的滤波器在该模型里**必须**是强正 NR —— 训练的定义就是如此。
实测不是。**所以 `main.exe` 的正向模型 ≠ `generate_bank.py` 的训练模型。**

再看：离线库与真机库在 `main.exe` 里**都**失败、`GFANC_SEC_NORM` 两档**都**不工作
→ **`main.exe` 当前哪个世界都没复现对，它无法给任何库打分。**

**⚠ 因此**: 在修好 `main.exe` 的正向模型之前，**任何"离线 dB"都不可引用**（不只是
不能当绝对值 —— 是连排序都不成立）。给槽打分只能用**真机同时段 A/B**。

### 4.4 真机同时段 A/B —— **slot 3 有效，但只有 ~0.5dB**（2026-09-17）

**方法**: `export/make_ab_bank.py --slot 3` → `data/wc_bank_ab_slot3.bin`
（7 槽：偶数槽 = 当前库 slot 3 的系数，奇数槽 = 全零）。
`GFANC_BANK_SIM=1 GFANC_BANK_SIM_SEC=5` 让程序每 5 秒自动换槽，
**同一段连续时间里 ANC 一直在开/关之间切** → 漂移同时作用于两边，相减抵消。

log 里 `anti` 列干净地分开两种状态（全零槽 `anti=0.0001`，slot3 槽 `anti≈0.10`），
`out: 峰值` 同步在 0.000 / ~0.4 之间跳。**A/B 机制确认工作正常。**

**读法**: 取每段 crossfade 之后的稳定行，配对相邻的 开/关。

| 相邻对 | ANC 开 ch1 | ANC 关 ch1 | ch1 降 | ch2 降 | ch3 降 |
|---|---|---|---|---|---|
| 槽0 vs 槽1 | 0.2203 | 0.2353 | **0.57 dB** | 0.19 | 0.47 |
| 槽2 vs 槽3 | 0.2159 | 0.2325 | **0.64 dB** | 0.64 | 0.81 |
| 槽4 vs 槽5 | 0.2206 | 0.2274 | **0.26 dB** | 0.48 | 0.54 |
| 槽6 vs 槽5 | 0.2227 | 0.2274 | **0.20 dB** | 0.45 | 0.53 |

**4 对全部同向**（开的那段总是低于相邻关的那段）→ **方向可信，不是漂移。**
但幅度只有 **0.2–0.8dB**，跨三个误差麦平均 **≈0.5dB**。

**这 0.5dB 的物理含义**（这是本轮最有用的一条）:
设开时 `err²=0.2203²=0.04853`，关时 `dis²=0.2353²=0.05537`，
则被抵消掉的功率 = `dis²−err² = 0.00684` → 相干抵消量 RMS = `√0.00684 = 0.083`。
归一化抵消系数 `|C| = 0.083 / 0.2353 = 0.352`。

**→ anti 确实相干地到达了误差麦，但幅度只有需要的 35%（差 2.8×，或等效相位差 ≈69°）。**

**关键推论**:
部署回放的通路和标定时**完全一样**
（`ref → Wc → 喇叭 → 声学 → 误差麦`；fixed 下 `dsp_delay` 根本不参与放音，
只用于建 Ŝ 给自适应用）。所以**只要存的 Wc 真是闭环收敛解，
冻结回放的取消量就必须和收敛那一刻相同**。实测差 2.8 倍
→ **存进槽里的 Wc 不是收敛解。**

**首要嫌疑**（都能在代码里指到）:
- `main_realtime.c:524-533` — `peak_mute` 上升沿在 **adapt 下把整个 Wc 乘 0.5**
  （`if (!anc_fixed()) { ctx->fx.wc[i] *= 0.5f; }`），且**不打眼地重复发生**。
  削顶 2 次 = ÷4 ≈ 2.8× 的缺口量级。见 [[anc-tone-test-level-trap]]。
- `main_realtime.c:438-445` — `safety_mute || peak_mute` 期间**每采样**乘
  `(1−WC_MUTE_DECAY)`（注释：半衰期 ~0.25s）。持续 1 秒静音 → Wc 只剩 1/16。

**注意**: 本轮 deploy 日志里**没有** `⚠ peak_mute 触发` 行 → 这两次部署运行没有削顶。
嫌疑落在**标定那一次**，需要标定日志才能确认。

**待办**: 重跑一次 band_3 的 adapt，记三个数：
① 闭环收敛时的 `anti` RMS（对上 0.10 就是定案）② 收敛 `NR` ③ 有无 `⚠ peak_mute 触发 N 次`。

### 4.5 CNN 决策层响应性确认（2026-09-17，同批实验）

`data/wc_bank.bin`（7 槽真库）+ band_3 噪声，全程 `类=3/7` 稳住。
中途播放 band_2 片段时日志出现 `class 3 → 2 (slot 2)`，切回 band_3 后
`class 2 → 3 (slot 3)`。**独立佐证**（不是只凭人工标注）：切换前后
`refFilt` 由 0.0425 掉到 0.0199 再回到 0.0337、`anti` 由 0.086 掉到 0.039 再回到 0.048
—— 参考谱确实移出/移回了 band_3 通带。**CNN 跟着真实噪声变，决策层可用。**

⚠ 该 run 后半段扰动变了（ch1 由 0.24 爬到 0.60、refFilt 掉到 0.020），
**绝对电平不可与 4.4 的 run 比较**，只能用来判"选槽对不对"。

### 4.3 现场部署日志（250Hz 单音，`GFANC_ANC_MODE=fixed`）

```
[ANC] INIT Wc=库槽0 (ramp 800ms, mute_hold 1500ms)
       Auto gain=1.0x from ref_rms=0.0601
       out: 峰值 0.169 (距膝点0.9 +14.5dB)  触膝 0.000%     ← 输出被冷启动压到 0.12
[BANK] 类=0/7 NR=n/a anti=0.0781 ... raw: ch0(ref)=0.0479 ch1=0.3511 ch2=0.2835 ch3=0.2884
  [BANK] class 0 → 3 (slot 3, fade 1600)                   ← 第 1 秒末就换槽
       out: 峰值 0.994 (距膝点0.9 -0.9dB)  触膝 2.745%     ← 到此时才放开
[BANK] 类=3/7 NR=n/a anti=0.4162 ... raw: ch0(ref)=0.0482 ch1=0.2207 ch2=0.1912 ch3=0.2188
（此后 anti 衰减并稳定在 ≈0.166~0.170，ch1 稳定在 ≈0.22~0.24）
```

- **输入电平**: `ref ch0 ≈ 0.048`，全程稳定
- **时间线要点**: 250Hz 单音 → CNN 判为**类 3** → 部署加载**槽 3**（band_3 宽带滤波器）。
  而**用 250Hz 单音标出来的是槽 0**（见 4.1）。槽 0 只存活 1 秒，
  且这 1 秒全程被冷启动限幅压着（`out: 峰值 0.169`），随后即被替换 ——
  **那套单音标定一帧都没满功率输出过**
- **与更早一次同电平日志（`ref ≈ 0.048`）对比**: 槽 3 稳定后 ch1 由 0.35~0.39
  降到 0.22~0.24，约 4dB。但残差漂移 2.6dB，此差异卡在漂移量级边缘，方向可信、幅度存疑

---

## 5. 尚不能回答 / 待核实

1. **NTU 的 10dB 到底是什么条件下的数** —— 哪个噪声、几点平均、仿真还是真机、
   是 `NR_true` 还是误差麦实测。**2026-09-17 复查: 论文闭源（Unpaywall `is_oa: False`），
   无开放副本，仓库 README 只给定性描述（"satisfactory noise reduction performance"），
   GitHub 仓库内也**没有**任何 dB 表或结果图**。
   → 这个数**至今没有被任何一手来源证实过**，待用户提供出处（截图/页码/哪篇论文）。
2. **本仓库部署的 NR 究竟是多少** —— 现在测不到（见 3.4）
3. **`dsp_delay = 190` 是否正确** —— 代码期望 4–6ms，实测 8.5–12.5ms 且历次未落区间
4. **槽 0 与槽 6 是否需要重标** —— 槽 0 是纯音遗留物（带内能量 1.4%）；
   槽 6 带内能量仅 60.8%。**但注意 4.2.1**：离线表不能判库好坏，重标前先要一个可信判据
5. **离线模型与真机标定是否同源** —— 见 4.2.1 的匹配槽悖论。这是决定"离线数字能不能用"的
   前置问题

---

## 6. 建议的验证顺序（按代价从低到高）

1. **让 fixed 模式能测自己的 NR**（见 3.4）—— **这一步应该最先做**。现在所有关于
   "部署到底降了多少"的讨论都缺一个真机数字，离线又已知不可信（3.5 + 4.2.1）。
   注意这是**行为变更**（会激活 `safety_mute` 静音链），需先列改动清单确认
2. **真机同时段 A/B**（`export/make_ab_bank.py`）—— 在拿到可测的 NR 之后，给库里的槽
   打分。**在此之前不要依据离线表重标任何槽**
3. **拿 band_3 噪声跑部署** —— 目前所有现场测试都用 250Hz 单音，而 CNN 把单音送到槽 3
   （band_3 滤波器）。用单音测频带库本身不是有效对比
4. **A/B 延迟**: `$env:GFANC_DSP_DELAY='0'` 跑一次部署对比 —— 验证 3.5 的影响量级
5. 重标槽（0 / 6）—— 等 2 给出的判据
6. 拓扑层面（次级源数量）留到最后

---

## 附: 来源

- **NTU 仓库源码（2026-09-17 已取得并逐文件读过）**: <https://github.com/Luo-Zhengding/SFANC-Window>
  取法: `curl -L -o sfanc.tgz https://codeload.github.com/Luo-Zhengding/SFANC-Window/tar.gz/refs/heads/main`
  文件清单: `Acquired_sound.py`、`Control_filter_selection.py`、`Loading_real_wave_noise_2D.py`、
  `Main_SFANC_Window.ipynb`、`Modified_ShufflenetV2.py`、`UDP_pxie_connector.py`、
  `ShuffleNetV2_Synthetic.pth`、`output.wav`。
  **注意: 无滤波器训练代码、无结果数据、无 dB 表。**
- 论文: <https://www.sciencedirect.com/science/article/abs/pii/S0888327024002620>（付费墙）
- NTU 机构库: <https://dr.ntu.edu.sg/entities/publication/c4b1dd92-c7ce-4285-b5bb-e3c42b45236f>（AWS WAF 拦）
- 同组 SFANC-FxNLMS（**摘要可读，含 3.8 的关键引用**）: <https://arxiv.org/abs/2208.08082>
- 同组不同 CNN 性能对比: <https://arxiv.org/abs/2208.08440>

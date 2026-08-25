# 路线决策 — 硬选库真实噪声重训 + CNN 对齐论文（马路噪声 10→4dB 回归分析）

> **日期**: 2026-08-25 · **类型**: 路线决策/备忘（为后续"走哪条路"做准备, 非结论）
> **相关**: [无误差麦方案_与SFANC对照_路线分析](无误差麦方案_与SFANC对照_路线分析.md)(SFANC vs 连续权重路线) · [论文知识_GFANC谱系与窗户ANC架构](论文知识_GFANC谱系与窗户ANC架构.md)(论文谱系) · [架构](架构.md)
> **数据来源**: 本会话实测 + [SFANC-Window](https://github.com/Luo-Zhengding/SFANC-Window) 源码浅克隆核实 + 用户本地 `D:\Dataset\*` 两套语料

---

## 〇、一句话结论

**马路噪声离线 NR 从旧分支 ~10dB 回落到现在的 ~4dB, 根因是"连续权重 Wc(宽带可整形) → 硬选 1/7 窄带槽"的架构切换, 不是路径/带通/CNN 训练错误。** 论文(开源 SFANC-Window)本身也是硬选架构; 它的 10dB 来自"真实宽带噪声训练的宽频带槽 + 专用实时硬件 + 与其匹配的评估噪声"。要拿回 10dB, 需要**把库槽换成"喂真实噪声"的槽**（`generate_bank.py` 注释原话: *想消什么噪声就喂什么*）；CNN 是否要改、怎么改, 取决于走哪条路线（见 §四）。

---

## 一、现象: 同文件、同 PC, 离线 NR 从 ~10dB 回落到 ~4dB

| 分支 | 部署形态 | `road_noise-15.wav` 离线 NR_true | 250Hz 纯音离线 |
|---|---|---|---|
| `scenezone-anc`（旧） | **连续权重**: CNN(direct_weight, K=30, tanh) 加权组合 15 条子滤波器 `sub_filters.bin` → 宽带 Wc | **~10dB**（用户实测） | — |
| `plan-c-dual-mode`（当前） | **SFANC 硬选**: CNN(K=7, argmax) 选 1/7 窄带库槽 `wc_bank.bin` → 只消一档 | **~4.7dB** | **23.5dB** |

### 1.1 关键内部对照（瓶颈定位）

- 两者都是 `main.exe` 离线跑、同 PC、**同样的路径/带通**；**离线仿真不叠加实时 12.5ms 环路延迟**（Wc⊗ref 直接算, causality 报告只是打印 τ, 不进入 anti）。
- 旧分支的 ~10dB 证明: **同一路径/同 PC 下, 宽带噪声离线可消到 10dB 级** → 不是 causality、不是路径、不是 CNN 选槽错。
- 唯一变量 = **Wc 频谱覆盖能力**: 连续权重可 7 带同时整形；硬选只消选中那 1 带。
- `road_noise-15.wav` 频谱（本会话实测, 50-1500Hz 内）: `50-200Hz:34% · 200-500Hz:20% · 500-1000Hz:30% · 1000-1500Hz:17%`, **近均匀**; 7 带(log 50-1500)单带最高只占 **21.8%**(band5 568-923Hz) → 单窄带槽理想消音上限 ~1-2dB, 实测 4.7dB 靠 CNN 0→6→1→6→5 分时切换多带 + 槽带外旁瓣才拼出来。
- 250Hz 纯音: 能量集中在 band3(215-349Hz) → 硬选可消 20dB+（离线实测 23.5dB）→ **库槽本身工作正常, 硬选架构在窄带/稳态噪声上是强的**。

> ⚠️ 与实时 250Hz"无降噪、扬声器输出小"**不是同一个问题**。实时 250Hz 的 anti 数字量已与离线预测一致(0.032 vs 0.0325), 失败在物理播放路径(输出通道路由/扬声器电平/标定增益一致性), 属硬件排查, 不在本文档路线内。

---

## 二、开源 SFANC-Window 核实（论文就是硬选架构, 不是"更高级"的架构）

源码浅克隆 `/tmp/sfanc` 逐文件核实（2026-08-25）:

### 2.1 架构 = 硬选, 与我们的部署形态一致

- `Control_filter_selection.py`: `Modified_ShufflenetV2(num_classes=7)` → `torch.argmax(prediction)` → 选 1/7 滤波器 ID → UDP 发 PXIe。**逐秒 1s 帧分类**, 与我们 1Hz CNN + 硬选库同构。
- `Modified_ShufflenetV2.py`: `bw2col`(1→10→3 通道 1×1 conv) → **ImageNet 预训练 ShuffleNetV2 x0.5** → conv5 改 192→512 → fc 512→7。输入 = **Mel 谱图 `[1,64,32]`**(`Loading_real_wave_noise_2D.py`: minmax → MelSpectrogram(n_fft=1024, hop=512, n_mels=64) → `power_to_db`)。
- 仓库**只开源推理**; 固定滤波器训练、次级路径测量、CNN 训练循环、结果评估**均未开源**（README 原话: 7 条滤波器在 4 通道 ANC 窗上获取）。

### 2.2 论文为什么能 10dB 而我们 4dB（差异点, 已核实/推断分明）

| 差异 | 论文 | 我们 | 已核实? |
|---|---|---|---|
| 槽训练语料 | 7 段**真实宽带噪声**（"7 broadband noises with different frequency ranges"） | 合成窄带 `synth_noise/band_0..6.wav`（每带 ~1/7 log 十倍频程） | 论文 README 原文 / 我们 wc_bank_info.json |
| 评估噪声 | 论文自选噪声（演示视频/图, 若低频集中则单槽消大头） | `road_noise-15.wav` 频谱近均匀, 单带 ≤22% | 我们实测频谱 |
| 实时硬件 | PXIe-8135 实时控制器 + RTX3060 并行 CNN, **delayless**; 4 麦 4 扬, 47cm 窗 | PC 原型 3 麦 2 扬, 实时有 ~12.5ms 环路（离线无） | 论文代码/README + 我们 README |
| NR 指标 | 实时误差麦实测（付费正文图表） | 离线全频带 NR_true | — |

### 2.3 诚实边界

论文摘要/开源代码**未给出具体 dB**（摘要只写"satisfactory reduction for broadband and real-world noises"）。"10dB"来自用户引用（演示视频/付费正文图表）——**按用户陈述采信, 未逐字核实**。

---

## 三、语料盘点（用户本地已有两套）

### 3.1 `D:\Dataset\Synthetic_Dataset` = 论文**合成**训练语料

- 结构: `Training_data/`(60,000) + `Validate_data/`(10,000) + `Testing_data/`(5,000), 共 75,000 段 1s @16kHz, 命名 `synth_bb_*`.
- 标签: `Index_synth_*.csv` 列 = `File_path, category(=synthetic), gain_0..29`。**没有类别列** —— 7 类是**生成时按带通中心频率 fc 落在哪档**定义的, 不在 CSV 里; 那 30 个 gain 实测(质心相关 -0.44) **不能直接推类别**。
- 频谱: 抽验为"白噪→单带通"合成特征（rms≈0.72, 单能量峰 1251/469/967Hz）。
- 用途: 训"频率范围分类"CNN 的语料（论文方式）, 或作为喂槽语料（单带通, 窄）。

### 3.2 `D:\Dataset\Real_world_Dataset` = 论文**真实世界**语料

- `raw/{children, construction, other, railway, road, square_dance, street}/` — 7 类语义真实录音（16kHz）:
  - children 8.0h / construction 5.7h / railway 7.1h / **road 2.3h（8 有效文件 + 3 个非 RIFF 坏文件）** / street 1.98h / other 0.68h / square_dance 0.12h; 共 ~26h.
- `Training_data/` 63,374 段 1s 切片, `Index_real_Training_data.csv` 带 `category` 列 = **语义类**（children/construction/railway/road 各 ~16k/15.4k; street/square_dance/other **未进 Training**）; `SoftLabels_real_*.npy` (63374,3) 3 维软标签; `Gains_real_*.npy` 30 维.
- 频谱: 1s 切片确为**真实宽带噪声**; **road 切片段间差异大**: 有的低频主导(84% 在 50-200Hz), 有的中频(40% 在 500-1000Hz), 有的近均匀——与 `road_noise-15.wav` 同量级.

### 3.3 关键结论

`raw/road` 是**宽带且可变**, 不是低频集中 → **没有任何单条窄带槽能覆盖它的主要能量** → 这是"为什么带限切片方案只能到 5-7dB"的物理原因。

---

## 四、两条路线（决策主体）

### 路线 A — 带限槽（论文字面做法）→ 预期 ~5-7dB, **CNN 不用改**

- 把真实噪声按 7 带(log 50-1500Hz)切片喂 `generate_bank.py --filters road_band_0..6.wav`.
- 新库仍"槽 k = 频带 k", **保持频带边界与槽序** → 现有 CNN 隐式学的就是频率范围分类 → **不用重训**（论文迁移性在此体现）。
- 局限: 马路噪声能量摊在 7 带, 单带最多 ~22% → 总 NR 上不去 10dB.

### 路线 B — 全频带 road 槽（冲 10dB）→ **CNN 必须改**

- 训一条喂 `raw/road` **全频带**的宽带槽, 它才能整段抵消平坦马路噪声（旧连续权重分支 10dB 证明上限存在）。
- 代价: 槽不再是"频带"结构 → CNN 需要能**选中 road 这类** → 二选一:
  - B1: CNN 换成语义分类（7 语义类）, 用 `Real_world_Dataset`（soft labels + gains 已备好）重训;
  - B2: CNN 保持频率范围分类, 但接受它不会专门为 road 选槽（若 road 能量分散, 选哪档看运气）——**不推荐**。
- 这是完整工程: CNN 重训 + 7×FxLMS 槽重训 + 导出 + C 端（若换 2D CNN 则 C 端推理也要改）。

### 4.1 决策树

```
目标=马路噪声回 10dB?
├─ 先做最小验证(§六): 1 条 road 全频带槽 + 单槽库离线测 → 若 ~10dB, 架构没问题, 问题在"槽没喂真实噪声"
│    └─ 是 → 决定走 A 还是 B
│         ├─ A(带限槽, 快, 5-7dB): 切片真实噪声重训 7 槽, CNN 不动
│         └─ B(全频带 road 槽, 10dB, 工程大): 重训槽 + CNN 改语义分类(B1)
│    └─ 否(验证出来不是 10dB) → 说明上限在别处(路径/增益/几何), 先查硬件, 别动 CNN
└─ 目标只是"论文对齐"(迁移性/可解释 LayerCAM/复现):
    → 路线 A + CNN 换 Modified_ShuffleNetV2 + Mel(§五), 但 10dB 不等于自动获得
```

---

## 五、CNN 与论文的差异 + 关键洞察

| 维度 | 我们 `m5_scene` (`train_real_bank_cnn.py`) | 论文 `Modified_ShufflenetV2` |
|---|---|---|
| 架构 | 1D 残差卷积 ~100K | 2D ShuffleNetV2 x0.5, **ImageNet 预训练** |
| 输入 | 原始波形 `[1,16000]`, 带通 50-1500 + minmax | **Mel 谱图 `[1,64,32]`**(minmax→MelSpectrogram→dB) |
| 标签 | `filter_idx` = 离线 FxLMS 打分"哪条槽消得最好"（**耦合当前库**） | **频率范围**（生成时 fc 定, **与库解耦**） |
| 训练数据 | 打分标签 CSV + 任意噪声 | 8 万段合成带通噪声 |
| 损失 | CrossEntropy（硬标签, 类均衡采样） | CrossEntropy（从论文文本推断, 训练循环未开源） |

**关键洞察——标签耦合性**: 我们的标签=槽号（打分而来）, 耦合当前库; 论文标签=频率范围, 与库解耦。但**我们的槽按频带排**, CNN 隐式学会的就是频率范围分类 → **只要新库保持同样的频带边界和槽顺序, CNN 不必重训**。这是"换库后 CNN 是否失效"的判断依据。

**彻底对齐论文的清单**（若选）: ① 模型 → `Modified_ShufflenetV2`（代码在 `/tmp/sfanc/Modified_ShufflenetV2.py` 可移植）; ② 输入 → Mel 预处理（`/tmp/sfanc/Loading_real_wave_noise_2D.py` 可移植）; ③ 标签 → 频率范围（用 `Synthetic_Dataset`）; ④ **C 端推理改 2D**（`cnn_bank_*.bin` 现在是 1D 权重, main.c/main_realtime.c 的 CNN 推理 + Mel 计算都要重写/新导出）。

---

## 六、最小验证计划（先确认 10dB 上限存在, 避免白干）

> 训练重计算（60s/槽 FxLMS）由用户跑, 不做只跑验证。

```bash
# 1. 拼接 raw/road 有效文件 → 一条连续全频带训练语料（跳过 3 个非 RIFF 坏文件）
# 2. 训 1 槽库（N=1 → main.c 走静态模式恒播槽 0, 绕过 CNN, 无需改代码）
python export/generate_bank.py --filters road_full.wav -o data/wc_bank_1slot.bin --train-sec 60
# 3. 备份现库 → 换 1 槽库 → 离线验证（槽0=road）
cp data/wc_bank.bin data/wc_bank.bin.bak
cp data/wc_bank_1slot.bin data/wc_bank.bin
./main.exe "Noise Examples/road_noise-15.wav"
# 4. 验证完还原
cp data/wc_bank.bin.bak data/wc_bank.bin
```

预期: 若 NR_true ≈ 10dB → 架构+路径都没问题, 问题是"槽没喂真实噪声", 走 §4.1 决策树; 若还是 ~5dB 以下 → 先查路径/增益/几何（校准与运行同旋钮等）, 别动 CNN。

---

## 七、待办 / 决策项清单

- [ ] 写 `raw/road` 拼接脚本（跳过非 RIFF 坏文件）, 可加按带切片选项（路线 A 用）
- [ ] 跑 §六 最小验证, 记录结果, 再定路线 A/B
- [ ] 若走 B1: 用 `Real_world_Dataset` 重训语义 CNN（soft labels + gains 已备）→ 导出 → C 端 2D 推理改造
- [ ] 若走"论文对齐": 移植 `Modified_ShufflenetV2` + Mel 预处理 + 频率范围标签 + C 端推理
- [ ] 核对 `raw/road` 3 个坏文件是否需要修复（若 road 时长不够训练）

---
*本文档为决策准备记录, 未落地代码。涉及的重计算(CNN 训练 / FxLMS 槽训练)按项目约定由用户执行。*

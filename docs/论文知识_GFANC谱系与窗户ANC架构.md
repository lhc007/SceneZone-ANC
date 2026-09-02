# 论文知识总结 — GFANC 谱系与窗户 ANC 架构

> **日期**: 2026-08-13 · **类型**: 第四类(论文知识: 各解决什么问题、用什么方式)
> **相关**: [窗户ANC可行性-因果限制_实测_方案](窗户ANC可行性-因果限制_实测_方案.md)(可行性/落地) · [SceneZone_综合审查报告_合并版](SceneZone_综合审查报告_合并版.md)(审查归档) · [无误差麦方案_与SFANC对照_路线分析 §12](无误差麦方案_与SFANC对照_路线分析.md)(2026-08-25 论文办法 vs 本项目 CNN/库的差异落地, 原独立决策文档并入)

---

## 一、论文谱系（NTU 组: Luo Zhengding / Shi Dongyuan / Gan Woon-Seng）

**一条进化链**，每篇补前一篇的短板:

```
SFANC(选固定滤波器,离散) → GFANC(生成滤波器,连续) → GFANC-Bayes/Kalman(帧间平滑)
    → Unsupervised-GFANC(无监督训练) → GFANC-FxNLMS+OCG(混合+在线聚类)
```

| 论文 | 出处 | 解决什么问题 | 用什么方式 |
|---|---|---|---|
| **SFANC-Window** | MSSP 2024, 214:111364 | 固定滤波器不灵活(每种噪声一个)、FxLMS 收敛慢易发散 | 1参考麦+4扬声器(周边)+4误差麦(仅训练)；ShuffleNetV2 从 7 个固定滤波器里**选 1**；开环前馈,运行时无误差麦 |
| **GFANC** | ICASSP 2023, arXiv 2303.05788 | SFANC **离散选择**的局限(噪声连续变化时选不准) | 子滤波器库 + 1D CNN 生成**组合权重**,线性组合出**任意**滤波器——"生成"替代"选择" |
| **GFANC-Bayes** | TASLP 2023, 32:1048 | CNN 帧间权重**抖动** | 在 GFANC 上叠 **Bayesian 滤波**,用相邻帧相关性平滑权重 |
| **GFANC-Kalman** | SPL 2024, 31:276 | 同 Bayes(帧间平滑) | CNN-Kalman 滤波替代 Bayesian |
| **Unsupervised-GFANC** | ICASSP 2024, arXiv 2402.09460 | GFANC **监督训练需标签**(昂贵+标注误差) | 端到端可微系统,用**累计平方误差(误差麦 err²)直接当损失**,不要标签 |
| **GFANC-FxNLMS+OCG** | ICASSP 2026, arXiv 2601.15889 | 混合后 GFANC 每帧**重置 FxLMS 打断收敛**→不稳定 | GFANC 帧级给起点 + FxLMS 采样级自适应 + **在线聚类(OCG)**判断是否真切换,只真切换才更新 |

### 1.1 SFANC-Window 详解（本项目架构"母论文"）

- **硬件**: 1 参考麦 + 4 扬声器(窗户四周相对,方形环绕) + 4 误差麦(仅训练) + NI PXIe 实时单元。
- **训练**: 7 种不同频段宽带噪声 → 让 4 误差麦声压最小化 → 反解 7 个固定滤波器;8 万条合成带通噪声 → 训 CNN 分类"选哪个滤波器"。
- **实时(开环)**: 参考麦采 1s → Mel 语谱图 [1,64,32] → ShuffleNetV2 → 选 ID → UDP 发 PXIe → 固定滤波器前馈 → 4 扬声器。**误差麦不参与**。
- **delayless 精髓**: CNN(慢链路,帧率) 与实时控制器(快链路,采样率) **两条链路并行**,选择结果只在帧边界交接,不打断实时控制。
- **降噪数值**: 摘要**未给具体 dB**(只说"宽带+真实低频噪声满意降噪"),数值在付费正文图表。
- **代码**: [SFANC-Window](https://github.com/Luo-Zhengding/SFANC-Window) **只开源推理**(CNN 选滤波器 + UDP),**训练固定滤波器/次级路径测量/结果评估都未开源**。

#### 1.1a SFANC-Window 训练方法 —— 关键的两层结构（合并自原架构.md 草稿）

**"滤波器类别怎么区分？"要分两层看，别混**:

① **CNN 分类器 = 纯合成数据训练**：
- 80,000 条 1s 噪声，全部是白噪声 → 随机带通滤波器生成的合成噪声
- 每类标签 = 一个频带范围（class k ↔ 频带 k）
- 输入是 **2D CNN（Modified_ShuffleNetV2, num_classes=7）**：Mel 频谱图（1s → MelSpectrogram → 64×32 灰度图），非时域波形
- 用 ImageNet 预训练 shufflenet_v2_x0_5 微调

② **7 条控制滤波器 = 真实声学收敛**：
- 论文 README 原文: *"7 pre-trained control filters are obtained in the 4-channel ANC window... 7 broadband noises with different frequency ranges are used as primary noises"*
- 即 7 条滤波器在真实 ANC 窗户硬件上，用 7 段不同频段宽带噪声做主噪声，逐段离线/在线 FxLMS 收敛得到——**滤波器真实（经真实声学路径），驱动它们的噪声是合成的**
- 类 k ↔ 滤波器 k 通过 **频带对齐**：第 k 类合成噪声的频带 = 第 k 条滤波器训练的噪声频带

**对本项目的影响 —— 架构选择不必复制，数据生成已对齐**：
- 论文是 2D CNN(Mel 图)，本项目是时域 **1D CNN（m5_scene）**吃 16000 样本波形。架构不同，但**核心 = 复刻它的数据生成方法**（`generate_synthetic_noise.py`：白噪→butter 带通、按频带定类），这一层已经对齐
- 现有对照:合成方法(白噪→带通)✅ / 标签(按频带定类)✅ / 训练规模(可调) / 每类滤波器(→ band_k.wav 喂槽)✅
- 论文标题对上了: *Real-time Implementation and Explainable AI Analysis of Delayless CNN-based Selective Fixed-filter ANC*（MSSP 2024）。核心贡献与本项目一致: **delayless**(无逐样本在线自适应,CNN 慢速选滤波器) + **selective fixed-filter**(固定滤波器库+选择=SFANC 硬选) + Markov 理论 + LayerCAM 可解释性。数据/训练方法没有额外的东西。

> ⚠️ 2D ShuffleNetV2 vs 本项目 1D m5_scene 的完整差异对照与"换库后 CNN 是否失效"判据，已并入 [无误差麦方案 §12](无误差麦方案_与SFANC对照_路线分析.md)（2026-08-25 决策分析）。

### 1.2 GFANC 原论文（曾为本项目 direct-weight 线的来源，2026-08-22 移除）

- **核心**: 完美重构滤波器组把预训练宽带滤波器分解成**子滤波器库(sub-filter bank)**;1D CNN 输出**组合权重**,线性组合生成任意滤波器。
- **关键性质**: **路径(子滤波器) 与 噪声(CNN 组合权重) 解耦** → 换环境只重标定子滤波器,CNN 不变(迁移性好)。
- **双速率**: CNN 帧率(协处理器) + 控制器采样率,delayless。
- 本项目**曾**以 direct-weight 架构(CNN 生成 K=30 子带 gains → 组合子滤波器 → Wc)实现 GFANC；**2026-08-22 随"清理回归 CNN 线"移除**，现行只留 SFANC 硬选库。此处仅作谱系记录。

### 1.3 GFANC-FxNLMS + OCG（曾落地于本项目，2026-08-22 移除）

- **混合动机**: GFANC 快但不稳 / FxLMS 稳但慢,互补。
- **混合的坑**: GFANC 每帧重新生成权重,微小变化也**重置 FxLMS** → 自适应被打断 → 震荡。
- **解法**: **在线聚类(OCG)**——CNN 预测权重做多质心聚类,**只有簇索引真变(噪声类别真切换)才更新滤波器**,簇内抖动不触发重置。
- **结果**: 飞机噪声 + 20-2000Hz 宽带下,有聚类版更平滑、误差更低;CNN 仅 0.21M 参数,只需 1 个预训练宽带滤波器。
- **对应本项目**: 曾以 `ocg.c`(tau/alpha/max_clusters/hold) 实机验证(250↔1000 双向真切换+簇复用+零 rescue)；**2026-08-22 随"清理回归 CNN 线"整体移除**，现行只保留 SFANC 硬选库单一架构（见 README / 无误差麦方案文档）。

### 1.4 Unsupervised-GFANC（开环转型最省标签的路）

- 监督 GFANC 需"标签=该噪声的最优组合权重",标签要离线让误差麦最小化来算(昂贵+偏差)。
- Unsupervised 把协处理器+控制器拼成**端到端可微系统**,用 err² 直接当损失,**不要标签**。
- **训练时仍要误差麦(损失靠它),运行时照样可开环拆掉**。
- 对开环的意义: 若走开环,CNN 训练目标需从"初始 Wc"改成"最优 W",Unsupervised 是最省标签的那条路。

---

## 二、本项目在谱系中的位置

> ⚠️ **现状注(2026-08-22 后)**: 现行架构 = **SFANC 硬选库单一架构**(对标 SFANC-Window):CNN(K=7) argmax 每秒选 1/7 成品槽 → crossfade,无误差麦部署(fixed 开环);标定 = 真机 adapt 逐槽收敛(FxLMS 仍用,见 [无误差麦方案 §11](无误差麦方案_与SFANC对照_路线分析.md))。下表"已实现"按**历史曾落地 + 现行仍留**两类标注——回归 CNN/连续权重线已整体移除,仅作谱系记录。

**曾落地 / 现行保留**:

| 组件 | 对应论文 | 现行状态(2026-08-22 后) |
|---|---|---|
| FxLMS 闭环自适应 | GFANC-FxNLMS | ✅ 保留:标定(adapt)用;VS-LMS/自适应 leak/anti-windup 在 `fxnlms_mimo.c` |
| 在线次级路径辨识 | — | ✅ 保留(`sec_online.c`);标定支路,部署开环不用 |
| 啸叫检测/安静检测/发散救援 | **论文没有**的工程加固 | ✅ 保留(`howling_detect.c` 等) |
| GFANC generative(子滤波器库+CNN 组合权重 = direct-weight) | GFANC / GFANC-Bayes | ❌ **2026-08-22 移除**,现行只留 SFANC 硬选 |
| OCG 在线聚类 | GFANC-FxNLMS+OCG | ❌ **2026-08-22 移除** |
| 反馈对消 | — | ❌ 实机发散暂弃(`calibrate_feedback.c` 仅标定工具残留) |
| 在线 Wc 自适应→连续组合 | Unsupervised-GFANC(理念) | ❌ 同上移除 |

**还差的(对实际降噪的作用,与现行路线关系)**:

| 差的部分 | 作用 | 现行路线是否触及 |
|---|---|---|
| Unsupervised 无监督训练(现在打标签监督) | 小:省标签工程,不改推理架构 | 未触及(仍监督训练 CNN) |
| GFANC-Bayes/Kalman 帧间平滑 | 无:OCG 已替代(同一问题不同解法) | 已随 OCG 移除,不再需要 |
| **多通道窗户扩展(8spk/8mic MIMO)** | **决定性**:窗户开口降噪需空间采样;当前 3麦2扬(标定)只验证了算法 | 远期目标板,见 [板级硬件定制需求](板级硬件定制需求_8S8E_闭环.md) |
| 开环能消**宽频带/近均匀**噪声 | 硬选窄带槽一次只消一档,马路噪声被摊平 → NR 受限 | 已用**真机标定槽**(合成/真实宽带标定信号)缓解,见 [无误差麦方案 §12](无误差麦方案_与SFANC对照_路线分析.md) |

---

## 三、窗户 ANC 架构核心知识

### 3.1 开口尺寸 → 频率上限 → 通道数(两条法则,互相印证)

**法则① λ/2 空间采样**: `f_max = c / (2 × 间距)`;周边布置 `间距 = 周长 / 扬声器数`。

**法则② 矩形波导模式数**: 透过开口的声场展开为模式,控制声场=控制主导模式。模式截止频率
`f_c(m,n) = (c/2)·√((m/a)² + (n/b)²)`,a/b 为开口两边。独立次级源数 ≈ 主导传播模式数。

**123×45cm 窗**(c=343):

| 频率 | λ | λ/2 间距 | 4 源(周长间距84cm) | 8 源(42cm) | 传播模式数 |
|---|---|---|---|---|---|
| 139Hz | 247cm | 123cm | ✅ | ✅ | 2 |
| 200Hz | 171cm | 86cm | ⚠️ | ✅ | ~3 |
| 380Hz | 90cm | 45cm | ⚠️刚好 | ✅ | 4 |
| 500Hz | 69cm | 34cm | ❌ | ⚠️刚好 | ~10 |
| 1000Hz | 34cm | 17cm | ❌ | ❌ | ~24-30 |

**结论**: 4 源 ≈ 380Hz、8 源 ≈ 500Hz、1000Hz 需 20-24 源。误差麦数须 ≥ 扬声器数(MIMO 解耦)。

### 3.2 边缘环绕 vs 铺面(两种路线)

| | 边缘环绕(SFANC-Window 4 大扬声器) | 铺面(Lam 2020 24 小扬声器) |
|---|---|---|
| 源数 | 少(4-8) | 多(20-24) |
| 优势频段 | **低频**高效(低阶模式极值在边缘) | **中高频**(800-1000Hz) |
| 高频上限 | 低(受边缘间距约束) | 高(面内采样密) |
| 低频效率 | 高(大口径大位移) | 差(小喇叭推不动 <300Hz) |

**论文 4 个够的原因**: 只做**低频** + 宿舍小窗(47×47cm),不是宽带;大扬声器是为低频体积位移,非为采样。

### 3.3 开环 vs 闭环

| | 开环(SFANC) | 闭环(本项目 FxLMS) |
|---|---|---|
| 误差麦 | 仅训练,运行时拆 | 运行时持续自适应 |
| 稳态降噪量 | = 闭环稳态(固定滤波器=收敛解) | 同左 |
| 路径漂移(窗户开合/家具/温度) | **无法自适应**,失配 | 能追,鲁棒 |
| 部署 | 简单(不留误差麦) | 要误差麦常驻 |

**折中**: 误差麦**按需标定**(安装时测Ŝ+训滤波器,标完拆),设备装好后不动 → 兼顾"不留"与"抗漂移"。

### 3.4 量产模式

- **每家都要标定**(次级路径 P/Ŝ 每家不同),但可**自动化成"安装自标定"**(几分钟)。
- **CNN 可复用**(噪声分类/组合权重映射与路径解耦),只重标定路径相关部分(固定滤波器/子滤波器库)。

### 3.5 关键物理结论速查

1. **8 扬声器 + 8 误差麦 → 20-500Hz 务实**,覆盖马路噪音主体(轮胎-路面噪声峰值 100-400Hz)。
2. **开窗场景玻璃不起隔声作用**: >500Hz 噪声直接通过开口漏入,ANC 采样不足又无玻璃兜底 → 纯漏。
3. **低频要大口径扬声器**(体积位移需求);中频小口径(4.5-8cm)高效。
4. **严格"整面声压=0"不可达**(需无限密集源+全频段),但控主导模式即可大幅降低透过开口的总辐射声功率。
5. **参考麦相干性**: 距离越远预览↑但相干↓;高频需参考阵列(间距~λ/2)。

---

## 参考资料

- Lam, Shi, Gan, Elliott & Nishimura, "Active control of broadband sound through the open aperture of a full-sized domestic window", *Scientific Reports* 10, 2020. https://link.springer.com/article/10.1038/s41598-020-66563-z
- Luo, Shi, Ji, Shen & Gan, "Real-time implementation and explainable AI analysis of delayless CNN-based selective fixed-filter active noise control", *MSSP* 214, 2024. 代码: https://github.com/Luo-Zhengding/SFANC-Window
- Luo et al., "Deep Generative Fixed-filter Active Noise Control", ICASSP 2023. arXiv:2303.05788
- Luo et al., "Delayless Generative Fixed-Filter ANC Based on Deep Learning and Bayesian Filter", *IEEE/ACM TASLP* 32, 2023.
- Luo et al., "Unsupervised Learning Based End-to-End Delayless Generative Fixed-Filter ANC", ICASSP 2024. arXiv:2402.09460
- Luo, Ma et al., "A Stabilized Hybrid ANC Algorithm of GFANC and FxNLMS with Online Clustering", ICASSP 2026. arXiv:2601.15889

# SceneZone ANC 快速入门

一个**主动降噪（ANC）系统**的纯 C 实现。部署时**不需要误差麦克风**，只需要参考麦克风和扬声器。

> **当前分支**：`plan-c-dual-mode`  
> **版本**：v2.1  
> **完整技术文档**：[docs/](docs/)

---

## 1. 两种工作模式

| 模式 | 命令 | 是否需要误差麦 | 作用 |
|------|------|---------------|------|
| **标定**（adapt，默认） | `.\scenezone_realtime.exe` | ✅ 需要 | 闭环自适应，收敛出降噪滤波器 |
| **部署**（fixed） | `$env:GFANC_ANC_MODE='fixed'; .\scenezone_realtime.exe` | ❌ 不需要 | 开环运行，加载标定好的滤波器库 |

**核心流程**：先用标定模式得到一组好用的滤波器，存进 `data/wc_bank.bin`；再用部署模式实时降噪。

---

## 2. 你需要什么

### 硬件

| 设备 | 数量 | 说明 |
|------|------|------|
| 多通道声卡（支持 ASIO，≥4 进 2 出） | 1 | 例如 BEHRINGER UMC 404HD |
| 参考麦克风 | 1 | 朝向噪声源 |
| 误差麦克风 | 3 | 放在要降噪的位置（**只在标定时用**） |
| 扬声器 | 2 | 播放反噪声 |
| Windows 电脑 | 1 | — |

### 软件

- GCC（Windows 通过 MSYS2 安装）
- Python 3 + numpy / scipy / pandas / torch / torchaudio
- 项目已自带 `data/*.bin`，不训练也能先跑通

---

## 3. 完整命令流（训练 → 实时运行）

按阶段 **0 → 1 → 2 → 3 → 4** 顺序执行。

> 如果只是先用现成模型跑通，可以跳过阶段 2 的训练。

---

### 阶段 0：准备环境

```bash
git clone https://github.com/lhc007/SceneZone-ANC.git
cd SceneZone-ANC

pip install numpy scipy pandas torch torchaudio
```

---

### 阶段 1：测量声学路径

> **为什么先测？** 训练生成滤波器库需要知道“扬声器到误差麦的声音是怎么传的”，这就是次级路径 Ŝ。换了硬件或摆放位置必须重测。

#### 1-① 编译校准程序

```bash
# 环路延迟测量
gcc -O2 -Iinclude src/calibrate_secondary.c -lm -o calibrate_secondary.exe

# 反馈路径测量（防啸叫）
gcc -O2 -Iinclude -D_WIN32_WINNT=0x0601 src/calibrate_feedback.c src/fir_filter.c src/binary_loader.c src/pa_loader.c -lm -lole32 -o calibrate_feedback.exe
```

#### 1-② 测次级路径 Ŝ（必做）

扬声器会发出扫频信号，误差麦接收，自动算出 `secondary_path.npy`。

```bash
cd SceneZone_Scene
python ../export/measure_secondary.py --interactive   # 首次：配置声卡
python ../export/measure_secondary.py                 # 正式测量
cd ..
```

> 产物：`SceneZone_Scene/Primary and Secondary Path/secondary_path.npy`

#### 1-③ 测主路径 Pri（可选，离线评估用）

```bash
cd SceneZone_Scene
python ../export/measure_primary.py --source-channel 0 --duration 8 --repetitions 4
cd ..
```

> 产物：`SceneZone_Scene/Primary and Secondary Path/primary_path.npy`

#### 1-④ 测环路延迟（首次 / 换声卡后必做）

```bash
.\calibrate_secondary.exe
```

> 产物：`data/sec_bulk_delay.bin`

#### 1-⑤ 测反馈路径（可选，防啸叫）

```bash
.\calibrate_feedback.exe
```

> 产物：`data/feedback_path_0.bin`、`data/feedback_path_1.bin`

---

### 阶段 2：生成滤波器库

> 滤波器库 `data/wc_bank.bin` 里存了 N 条成品滤波器（N=7 是默认值）。每条滤波器对应一类噪声。  
> 生成方式二选一：
> - **仿真版**：电脑离线算，不用误差麦
> - **真机标定版**：现场放噪声，用误差麦闭环收敛，效果更准

#### 2-⓪ 生成带通

```bash
python export/gen_bandpass_fir.py --f-low 50 --f-high 1500
```

> 产物：`SceneZone_Scene/models/bandpass_fir.mat`

#### 2-⑧ 生成滤波器库（两种方法，二选一）

##### 方法 A：仿真版（电脑离线算）

```bash
# 1. 生成 7 类合成噪声样本 + 自动标签
python export/generate_synthetic_noise.py --n-classes 7 --clips-per-class 2000

# 2. 离线生成滤波器库
python export/generate_bank.py --filters-dir data/synth_noise -o data/wc_bank.bin

# 3. 训练分类 CNN
python SceneZone_Scene/training/network/train_real_bank_cnn.py `
  --train data/bank_labels_train.csv `
  --valid data/bank_labels_valid.csv

# 4. 导出 C 二进制
python export/export_bin.py
```

##### 方法 B：真机标定版（推荐，效果更准）

需要先把实时版编译出来（见阶段 3），然后对 7 个槽逐个标定。

```powershell
# 槽 0：播放 data/synth_noise/band_0.wav，等 NR 稳定后按 Ctrl+C
$env:GFANC_CAL_INDEX='0'
.\scenezone_realtime.exe

# 槽 1：播放 data/synth_noise/band_1.wav
$env:GFANC_CAL_INDEX='1'
.\scenezone_realtime.exe

# ... 重复到槽 6
$env:GFANC_CAL_INDEX='6'
.\scenezone_realtime.exe

# 清理环境变量
Remove-Item Env:GFANC_CAL_INDEX
```

> 每跑完一次，系统会自动把收敛的滤波器保存到 `data/wc_bank.bin` 对应槽。  
> 7 个槽全部填完后，训练分类 CNN 并导出（同方法 A 的步骤 3、4）。

---

### 阶段 3：编译

#### 3-① 编译实时版

```bash
gcc -O2 -Iinclude -D_WIN32_WINNT=0x0601 main_realtime.c src/scene_controller.c src/scene_bank.c src/fxnlms_mimo.c src/fir_filter.c src/binary_loader.c src/cnn_m5_forward.c src/howling_detect.c src/sec_online.c src/pa_loader.c -lm -lole32 -o scenezone_realtime.exe
```

#### 3-② 编译离线评估版（可选）

```bash
gcc -O2 -Iinclude main.c src/scene_controller.c src/scene_bank.c src/fxnlms_mimo.c src/fir_filter.c src/binary_loader.c src/cnn_m5_forward.c -lm -o main.exe
```

---

### 阶段 4：运行

#### 4-① 标定模式（需要误差麦）

```powershell
.\scenezone_realtime.exe
```

- 播放稳态噪声（如白噪、粉噪、马路噪音）
- 看 log 里的 `NR` 数字，稳定后系统会自动保存
- 按 `Ctrl+C` 退出

#### 4-② 部署模式（不需要误差麦）

```powershell
$env:GFANC_ANC_MODE='fixed'
.\scenezone_realtime.exe
```

- 系统会自动识别噪声类型，从库里挑选对应的滤波器
- 每秒 log 会显示 `[BANK] 类=k/7`

---

## 4. 快速验证系统是否正常

**用 250Hz 纯音验证标定链路**：

1. 外部扬声器播放 250Hz 正弦波
2. 跑标定模式：`.\scenezone_realtime.exe`
3. 观察 log，如果 `NR` 能到 10dB 以上，说明系统正常

> 部署模式没有 NR 指标，验证靠人耳听 + 看 `[BANK]` 类号是否跟着噪声变化。

---

## 5. 常见问题

**Q：为什么 deploy 模式听不到降噪？**

A：最常见原因是库里的滤波器不是在你设备上标定的。先跑标定模式确认能降，再把收敛结果保存到库里。

**Q：标定 7 个槽一定要放 7 种不同噪声吗？**

A：是的。每个槽是一条独立的滤波器，对应一类噪声。可以用项目自带的 `data/synth_noise/band_0.wav ~ band_6.wav`，也可以用自己的录音。

**Q：什么时候需要重新训练 CNN？**

A：当你用**真实录音**（而非项目自带的合成噪声）标定库时，CNN 没见过这些录音的频谱，需要重训。如果用 `band_0~6.wav` 标定，一般不需要重训。

**Q：换硬件或摆放位置后要重做什么？**

A：重测次级路径（1-②）、环路延迟（1-④），并重新填库（阶段 2）。CNN 通常不用重训。

---

## 6. 详细技术文档

- 架构说明：[docs/无误差麦方案_与SFANC对照_路线分析.md](docs/无误差麦方案_与SFANC对照_路线分析.md)
- 变更记录：[docs/变更记录_CHANGELOG.md](docs/变更记录_CHANGELOG.md)
- 窗户 ANC 可行性：[docs/窗户ANC可行性-因果限制_实测_方案.md](docs/窗户ANC可行性-因果限制_实测_方案.md)

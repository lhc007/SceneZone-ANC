# calibrate_bank.ps1 — 7 槽真机标定 (逐槽自动跑通)
#
# 用法 (必须在仓库根目录):
#   .\calibrate_bank.ps1                      # 标全部 7 槽 (会问一次设备 ID)
#   .\calibrate_bank.ps1 -InDev 3 -OutDev 5   # 指定音频设备 ID, 全程不再问
#   .\calibrate_bank.ps1 -OnlySlot 3          # 只标槽 3
#   .\calibrate_bank.ps1 -CalSec 240          # 单槽标定跑久一点 (默认 150s)
#   .\calibrate_bank.ps1 -SlotTimeoutSec 300  # 脚本侧强杀上限调大
#
# 噪声源: **默认手动** —— 用 PC 之外的声源 (外部扬声器/手机) 循环放噪声,
# 脚本在每槽开始前停下等你按 Enter. 原因: 本机两个喇叭就是 ANC 自己在用,
# PC 上没有第三条输出能接噪声喇叭; 让 ffplay 放只会把噪声灌进 ANC 自己的喇叭.
# 若你的机器确实有独立于 ANC 的第三路输出, 可加 -AutoNoise 让 ffplay 代放.
#
# 设备 ID 从哪来: 单跑一次 .\scenezone_realtime.exe, 它会先打印设备列表再让你输 ID,
# 把当时输的那两个数记下来即可.
#
# 前提: 扬声器/功放已接好并开到标定音量; 参考麦/误差麦已接好 (adapt 模式需要误差麦).
# 每槽: 循环播 data\synth_noise\band_k.wav → adapt 模式跑 FxLMS → 收敛后 exe 自己
#       存库槽并退出 (GFANC_CAL_EXIT=1) → 脚本停播放 → 下一槽.

param(
    [int]   $SlotTimeoutSec = 200,
    [int]   $CalSec         = 150,   # 单槽标定墙钟秒数 (传给 GFANC_CAL_SECS, C 侧到点自退并保存)
    [int[]] $OnlySlot       = @(0, 1, 2, 3, 4, 5, 6),
    [int]   $InDev          = -1,
    [int]   $OutDev         = -1,
    [switch]$AutoNoise      = $false
)

$ErrorActionPreference = "Stop"

# 相对路径 (exe / data\) 都按仓库根算, 从别处调用也不会错
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$exe      = Join-Path $root "scenezone_realtime.exe"
$bankFile = Join-Path $root "data\wc_bank.bin"
$wavDir   = Join-Path $root "data\synth_noise"
$ffplay   = Get-Command ffplay -ErrorAction SilentlyContinue

# ── 清掉所有继承的 GFANC_* ──
# 2026-09-14 实测事故: 调用者 shell 里残留的 GFANC_BANK_FILE 让 exe 把标定结果写进了
# data\wc_bank_ab_slot0.bin, 而脚本查的是 data\wc_bank.bin → 标定明明成功却报"未标定",
# 白跑一轮. 逐槽那 6 个变量由循环自己设, 其余一律清掉, 不留任何隐藏残留.
# GFANC_BANK_SIM 尤其危险: 置 1 会让 exe 去轮换槽而不是标定.
$inherited = @(Get-ChildItem Env: | Where-Object { $_.Name -like 'GFANC_*' } |
               ForEach-Object { $_.Name })
foreach ($n in $inherited) { Remove-Item "Env:$n" -ErrorAction SilentlyContinue }
if ($inherited.Count) {
    Write-Host "已清除继承的 GFANC_* : $($inherited -join ', ')" -ForegroundColor DarkYellow
}

if (-not (Test-Path $exe))      { throw "找不到 $exe — 先跑 mingw32-make realtime" }
if (-not (Test-Path $bankFile)) { throw "找不到 $bankFile" }

# ── 设备 ID: 问一次, 7 槽复用 (exe 每槽都要, 不能让标定循环停下来等人按键) ──
if ($InDev -lt 0) {
    Write-Host "需要音频设备 ID (单跑一次 .\scenezone_realtime.exe 可看到列表)" -ForegroundColor Yellow
    $InDev = [int](Read-Host "  输入设备 ID (参考麦那一路)")
}
if ($OutDev -lt 0) {
    $OutDev = [int](Read-Host "  输出设备 ID (扬声器那一路)")
}

# ── 备份原库 ──
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
Copy-Item $bankFile "data\wc_bank.bin.bak_$ts" -ErrorAction SilentlyContinue
Write-Host "已备份原库 → data\wc_bank.bin.bak_$ts" -ForegroundColor DarkGray

function Start-Noise($k) {
    if (-not $AutoNoise) {
        # 手动: 噪声从 PC 之外的声源来 (外部扬声器/手机). 让 ffplay 放会把噪声
        # 灌进 ANC 自己的喇叭 —— 本机两个喇叭就是 ANC 在用, 没有第三路可用.
        Write-Host ">>> 【外部噪声源】请确保正在循环播放本轮噪声, 然后按 Enter" -ForegroundColor Yellow
        Write-Host "    (全量标定: band_$k.wav;  冒烟测试: 现有路噪素材即可)" -ForegroundColor DarkGray
        Read-Host "    播放好了按 Enter" | Out-Null
        return $null
    }
    $wav = Join-Path $wavDir "band_$k.wav"
    if (-not (Test-Path $wav)) { throw "文件不存在: $wav" }
    if ($ffplay) {
        Write-Host ">>> [AutoNoise] 循环播放 $wav"
        # -loop 0 = 无限循环; -nodisplay 不开视频窗
        return Start-Process -FilePath $ffplay.Source `
            -ArgumentList @("-loop", "0", "-nodisplay", $wav) `
            -PassThru -WindowStyle Hidden
    }
    Write-Host ">>> 未找到 ffplay, 请手动循环播放: $wav" -ForegroundColor Yellow
    Read-Host "按 Enter 继续 (确认已开始播放)" | Out-Null
    return $null
}

function Stop-Noise($proc) {
    # 手动模式 ($proc 为 $null): 不动外部声源, 由用户自己控制.
    if (-not $proc) { return }
    if (-not $proc.HasExited) {
        $proc | Stop-Process -Force -ErrorAction SilentlyContinue
    }
    # 兜底: 清理残留 ffplay (上一轮超时/异常退出留下的)
    Get-Process -Name ffplay -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
}

$okSlots   = @()
$failSlots = @()

for ($si = 0; $si -lt $OnlySlot.Count; $si++) {
    $k = $OnlySlot[$si]
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "  标定槽 $k" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan

    $proc = Start-Noise $k
    Write-Host ">>> 噪声播放已启动, 2 秒后开始标定..."
    Start-Sleep -Seconds 2

    # 标定必须钉死 mic 增益: 不设就走 auto-gain, 槽与槽之间基准不一致,
    # 且库是绝对增益, deploy 时串味 (见 docs/待办 第 1 条).
    $env:GFANC_ANC_MODE  = 'adapt'
    $env:GFANC_CAL_INDEX = "$k"
    $env:GFANC_MIC_GAIN  = '1.0'
    $env:GFANC_CAL_EXIT  = '1'   # 收敛写库后 exe 自退, 否则 & $exe 永久阻塞
    $env:GFANC_CAL_SECS  = "$CalSec"   # C 侧墙钟到点自退并保存 (进程永不退时的唯一保险)
    $env:GFANC_BANK_FILE = $bankFile   # 钉死写库路径 = 本脚本检查的那个文件
    # 设备 ID 走 stdin: exe 是 scanf 交互读取 (不认环境变量), Start-Process 用
    # -RedirectStandardInput 把两个数喂进去, 否则每槽都会停在提示上等人键.
    $devTmp = Join-Path $env:TEMP "gfanc_dev_$PID.txt"
    Set-Content -Path $devTmp -Value "$InDev`n$OutDev" -Encoding ascii

    Write-Host ">>> 写库目标: $bankFile  (槽 $k, 标定 ${CalSec}s)" -ForegroundColor DarkGray
    $t0 = (Get-Item $bankFile).LastWriteTime

    # Start-Process (而非 & $exe): 后者阻塞到进程退出, 收敛不了就永久挂死.
    # -NoNewWindow 让子进程继承当前控制台 → 实时输出仍可见.
    $p = Start-Process -FilePath $exe -NoNewWindow -PassThru `
         -RedirectStandardInput $devTmp
    Wait-Process -Id $p.Id -Timeout $SlotTimeoutSec -ErrorAction SilentlyContinue

    $timedOut = -not $p.HasExited
    if ($timedOut) {
        Write-Host ">>> 超时 ${SlotTimeoutSec}s 未收敛, 强杀 (本槽保持原值)" -ForegroundColor Yellow
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    }
    Stop-Noise $proc

    $t1 = (Get-Item $bankFile).LastWriteTime
    if ($timedOut) {
        $failSlots += $k
        Write-Host ">>> 槽 $k 未标定 (超时)" -ForegroundColor Yellow
    } elseif ($t1 -eq $t0) {
        $failSlots += $k
        Write-Host ">>> 槽 $k 未标定 (exe 退出但没写库 — NR 与 Wc 稳定都没达标)" -ForegroundColor Red
    } else {
        $okSlots += $k
        Write-Host ">>> 槽 $k 标定完成" -ForegroundColor Green
    }

    if (-not $AutoNoise -and $si -lt $OnlySlot.Count - 1) {
        Write-Host ">>> 下一槽 (槽 $($OnlySlot[$si + 1])) 请把外部声源换成 band_$($OnlySlot[$si + 1]).wav" -ForegroundColor DarkGray
    }
}

Remove-Item Env:GFANC_ANC_MODE, Env:GFANC_CAL_INDEX, Env:GFANC_MIC_GAIN, Env:GFANC_CAL_EXIT, `
    Env:GFANC_CAL_SECS, Env:GFANC_BANK_FILE -ErrorAction SilentlyContinue
if ($devTmp) { Remove-Item $devTmp -ErrorAction SilentlyContinue }

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  成功 $($okSlots.Count) 槽: $($okSlots -join ', ')" -ForegroundColor Green
if ($failSlots.Count) {
    Write-Host "  失败 $($failSlots.Count) 槽: $($failSlots -join ', ')  ← 重跑: -OnlySlot $($failSlots -join ',')" -ForegroundColor Red
}
Write-Host "========================================" -ForegroundColor Cyan

Write-Host "`n验证 deploy 模式命令:"
Write-Host '  $env:GFANC_ANC_MODE=''fixed''; $env:GFANC_MIC_GAIN=''1.0''; .\scenezone_realtime.exe' -ForegroundColor Yellow
Write-Host "回滚原库: Copy-Item data\wc_bank.bin.bak_$ts data\wc_bank.bin -Force" -ForegroundColor DarkGray

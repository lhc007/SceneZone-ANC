# calibrate_bank.ps1
# 7 槽真实设备标定脚本
# 用法: 右键 → 使用 PowerShell 运行，或在终端输入  .\calibrate_bank.ps1

$ErrorActionPreference = "Stop"

$exe       = ".\scenezone_realtime.exe"
$bankDir   = "data\synth_noise"
$ffplay    = Get-Command ffplay -ErrorAction SilentlyContinue

function Play-Noise($k) {
    $wav = "$bankDir\band_$k.wav"
    if (-not (Test-Path $wav)) { throw "文件不存在: $wav" }
    if ($ffplay) {
        Write-Host ">>> 自动循环播放 $wav"
        $proc = Start-Process -FilePath $ffplay.Source `
            -ArgumentList "-loop 0 -nodisplay `"$wav`"" `
            -PassThru -WindowStyle Hidden
        return $proc
    } else {
        Write-Host ">>> 未找到 ffplay，请手动循环播放: $wav" -ForegroundColor Yellow
        Read-Host "按 Enter 继续（确认已开始播放）"
        return $null
    }
}

function Stop-Noise($proc) {
    if ($proc -and -not $proc.HasExited) {
        $proc | Stop-Process -Force -ErrorAction SilentlyContinue
    }
    # 兜底：清理残留 ffplay
    Get-Process | Where-Object { $_.ProcessName -eq "ffplay" } `
        | Stop-Process -Force -ErrorAction SilentlyContinue
}

# 备份原库
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
Copy-Item "data\wc_bank.bin" "data\wc_bank.bin.bak_$ts" -ErrorAction SilentlyContinue
Write-Host "已备份原库到 data\wc_bank.bin.bak_$ts"

for ($k = 0; $k -lt 7; $k++) {
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "  标定槽 $k / 7" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan

    $proc = Play-Noise $k

    Write-Host ">>> 噪声播放已启动，2 秒后开始标定..."
    Start-Sleep -Seconds 2

    try {
        $env:GFANC_ANC_MODE = 'adapt'
        $env:GFANC_CAL_INDEX = "$k"
        & $exe
    } finally {
        Stop-Noise $proc
    }

    Write-Host ">>> 槽 $k 标定完成"
}

Write-Host "`n全部 7 槽标定完成！" -ForegroundColor Green
Write-Host "验证 deploy 模式命令:"
Write-Host '$env:GFANC_ANC_MODE=''fixed''; .\scenezone_realtime.exe' -ForegroundColor Yellow

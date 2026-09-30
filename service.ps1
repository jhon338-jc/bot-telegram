<#
.SYNOPSIS
    Kelola userbot Telegram sebagai service background (tanpa cmd window).

.DESCRIPTION
    Userbot ini memakai akun Telegram asli, jadi harus tetap tersambung ke
    internet. Skrip ini mendaftarkan supervisor (server.py) ke Task Scheduler
    Windows supaya:
      - otomatis hidup setiap kali kamu login,
      - berjalan tanpa jendela cmd sama sekali,
      - otomatis restart kalau child process mati.

    Tidak butuh NSSM, tidak butuh hak admin, tidak butuh password tersimpan.

.PARAMETER Action
    install  Daftarkan task + jalankan sekarang (default)
    start    Jalankan task yang sudah terdaftar
    stop     Hentikan task
    restart  Stop lalu start lagi
    status   Tampilkan status task + log supervisor
    uninstall Hapus task dari Task Scheduler

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\service.ps1 install
#>

param(
    [ValidateSet('install', 'start', 'stop', 'restart', 'status', 'uninstall')]
    [string]$Action = 'install'
)

$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TaskName = 'TelegramUserbot'
$Pythonw = Join-Path $ProjectDir 'venv\Scripts\pythonw.exe'
$Server = Join-Path $ProjectDir 'server.py'

function Test-Prasyarat {
    if (-not (Test-Path -LiteralPath $Pythonw)) {
        throw "pythonw.exe tidak ditemukan: $Pythonw`nBuat venv dulu: python -m venv venv"
    }
    if (-not (Test-Path -LiteralPath $Server)) {
        throw "server.py tidak ditemukan: $Server"
    }
}

function Install-Task {
    Test-Prasyarat
    $user = "$env:USERDOMAIN\$env:USERNAME"

    $action = New-ScheduledTaskAction `
        -Execute $Pythonw `
        -Argument ('"{0}" start' -f $Server) `
        -WorkingDirectory $ProjectDir

    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    # Beri jeda agar jaringan dan Telegram siap dulu sebelum login.
    $trigger.Delay = 'PT20S'

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -MultipleInstances IgnoreNew `
        -Priority 7

    $old = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($old) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Task lama diganti."
    }

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description 'Userbot Telegram (akun asli, Telethon) - background service.' `
        -User $user `
        -RunLevel Limited `
        -Force | Out-Null

    Write-Host "Task '$TaskName' terdaftar (auto-start 20 detik setelah login)."
}

function Start-Task {
    Test-Prasyarat
    $stopFile = Join-Path $ProjectDir 'data\stop.flag'
    Remove-Item -LiteralPath $stopFile -Force -ErrorAction SilentlyContinue
    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 3
    Write-TaskStatus
}

function Stop-Task {
    $stopFile = Join-Path $ProjectDir 'data\stop.flag'
    if (Test-Path -LiteralPath $stopFile) {
        Set-Content -LiteralPath $stopFile -Value (Get-Date -Format o) -Encoding ASCII
    }
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    }
    Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
        Where-Object { $_.CommandLine -like '*telegram-bot*' } |
        ForEach-Object {
            Write-Host "Menghentikan PID $($_.ProcessId)..."
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    Write-Host "Userbot dihentikan."
}

function Write-TaskStatus {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Host "Task '$TaskName' belum terdaftar. Jalankan: .\service.ps1 install"
        return
    }
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Host "Task     : $TaskName"
    Write-Host "Status   : $($task.State)"
    Write-Host "Terakhir : $($info.LastRunTime)"
    Write-Host "Hasil    : $($info.LastTaskResult)  (0 = sukses, 267009 = masih berjalan)"

    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
        Where-Object { $_.CommandLine -like '*telegram-bot*' }
    if ($procs) {
        Write-Host "Proses   :"
        $procs | ForEach-Object { Write-Host "  PID $($_.ProcessId) - $($_.Name)" }
    }
    else {
        Write-Host "Proses   : tidak ada (userbot tidak jalan)"
    }

    $serverLog = Join-Path $ProjectDir 'logs\server.log'
    if (Test-Path -LiteralPath $serverLog) {
        Write-Host ""
        Write-Host "--- logs\server.log (10 terakhir) ---"
        Get-Content -LiteralPath $serverLog -Tail 10
    }
}

switch ($Action) {
    'install'   { Install-Task; Start-Task }
    'start'     { Start-Task }
    'stop'      { Stop-Task }
    'restart'   { Stop-Task; Start-Sleep 2; Start-Task }
    'status'    { Write-TaskStatus }
    'uninstall' {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($task) {
            Stop-Task
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
            Write-Host "Task '$TaskName' dihapus."
        }
        else {
            Write-Host "Task '$TaskName' tidak ada."
        }
    }
}

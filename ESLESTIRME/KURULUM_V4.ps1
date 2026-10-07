$ErrorActionPreference = 'Stop'
try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'KURULUM BAT dosyasina sag tiklayip Yonetici olarak calistir secin.'
    }
    $dest = 'C:\Program Files (x86)\Pan Group\PanCafe Pro Client\upload'
    if (-not [IO.Directory]::Exists($dest)) { throw 'PanCafe upload klasoru bulunamadi. PanCafe kurulumunu kontrol edin.' }
    $csv = Join-Path $PSScriptRoot 'eski-isim-eslestirmeleri.csv'
    $rows = @(Import-Csv -LiteralPath $csv -Delimiter ';' -Encoding UTF8)
    if ($rows.Count -ne 79 -or @($rows | Group-Object 'Eski bilgisayar adı' | Where-Object Count -ne 1).Count -ne 0) { throw 'Eslesme listesi eksik veya tekrarlanan isim var.' }
    $files = @('KAMPUS_GAME_ARENA_KILIT_V4.bat', 'KAMPUS_GAME_ARENA_KILIT_V4.ps1', 'eski-isim-eslestirmeleri.csv')
    $images = @($rows | ForEach-Object { $_.'Görsel dosyası' } | Sort-Object -Unique)
    if ($images.Count -ne 21) { throw '21 gorsel bekleniyor.' }
    Add-Type -AssemblyName System.Drawing
    foreach ($name in $images) {
        if ([IO.Path]::GetFileName($name) -ne $name -or [IO.Path]::GetExtension($name) -ine '.jpg') { throw 'Gecersiz kaynak dosya adi.' }
        $img = $null
        try {
            $img = [Drawing.Image]::FromFile((Join-Path $PSScriptRoot $name))
            if ($img.Width -ne 1920 -or $img.Height -ne 1080 -or $img.RawFormat.Guid -ne [Drawing.Imaging.ImageFormat]::Jpeg.Guid) { throw ('Gecersiz gorsel: ' + $name) }
        } finally { if ($null -ne $img) { $img.Dispose() } }
    }
    $files += $images
    foreach ($name in $files) {
        $src = Join-Path $PSScriptRoot $name
        if (-not [IO.File]::Exists($src)) { throw ('Paket dosyasi eksik: ' + $name) }
    }
    foreach ($name in $files) {
        $src = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot $name))
        $out = [IO.Path]::GetFullPath((Join-Path $dest $name))
        if ($src -ine $out) { [IO.File]::Copy($src, $out, $true) }
        if ((Get-FileHash -LiteralPath $src).Hash -ne (Get-FileHash -LiteralPath $out).Hash) { throw ('Dosya dogrulanamadi: ' + $name) }
    }
    $psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $script = Join-Path $dest 'KAMPUS_GAME_ARENA_KILIT_V4.ps1'
    $arguments = '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $script + '"'
    $action = New-ScheduledTaskAction -Execute $psExe -Argument $arguments -WorkingDirectory $dest
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $taskPrincipal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
    Register-ScheduledTask -TaskName 'KampusArena_Kilit_V4' -Action $action -Trigger $trigger -Principal $taskPrincipal -Settings $settings -Description 'Eski PC adina gore kilit.png secimi; hata halinde mevcut dosya korunur.' -Force | Out-Null
    Write-Host 'KURULUM TAMAMLANDI: KampusArena_Kilit_V4 acilis gorevi olusturuldu.'
    Write-Host 'Mevcut kilit.png degistirilmedi. Eski V3 acilis gorevini kapatin.'
    Write-Host 'Kontrol icin upload klasorundeki BAT dosyasini -Kontrol ile calistirin.'
    Write-Host 'Acilis gorevi sirasi PanCafe ile otomatik olarak garanti edilmez; ilk yeniden baslatmada kontrol edin.'
    exit 0
} catch {
    [Console]::Error.WriteLine('KURULUM HATASI: ' + $_.Exception.Message)
    exit 1
}

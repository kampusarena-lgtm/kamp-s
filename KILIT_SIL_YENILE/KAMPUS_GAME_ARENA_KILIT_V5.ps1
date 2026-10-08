param([switch]$Kontrol)
$ErrorActionPreference = 'Stop'
$target = 'C:\Program Files (x86)\Pan Group\PanCafe Pro Client\upload\kilit.png'
$temp = $null
$img = $null
$backup = $null
$removed = $false
$oldAttributes = $null
try {
    $rows = @(Import-Csv -LiteralPath (Join-Path $PSScriptRoot 'eski-isim-eslestirmeleri.csv') -Delimiter ';' -Encoding UTF8)
    $matches = @($rows | Where-Object { $_.'Eski bilgisayar adı' -ieq $env:COMPUTERNAME })
    if ($matches.Count -ne 1) { throw 'Bilgisayar adi listede yok veya birden fazla eslesme var.' }
    $name = $matches[0].'Görsel dosyası'
    if ([IO.Path]::GetFileName($name) -ne $name -or [IO.Path]::GetExtension($name) -ine '.png') { throw 'Gecersiz gorsel dosya adi.' }
    # The installation package keeps images alongside this script.
    $source = Join-Path $PSScriptRoot $name
    if (-not [IO.File]::Exists($source)) { throw 'Kaynak gorsel bulunamadi.' }
    $targetDir = [IO.Path]::GetDirectoryName($target)
    if (-not [IO.Directory]::Exists($targetDir)) { throw 'PanCafe upload klasoru bulunamadi.' }
    Add-Type -AssemblyName System.Drawing
    if (-not $Kontrol) {
        $temp = Join-Path $targetDir ('kilit_new_' + [Guid]::NewGuid().ToString('N') + '.png')
        [IO.File]::Copy($source, $temp, $false)
        if ((Get-FileHash -LiteralPath $source).Hash -ne (Get-FileHash -LiteralPath $temp).Hash) { throw 'Kopya dogrulanamadi.' }
        $img = [Drawing.Image]::FromFile($temp)
    } else { $img = [Drawing.Image]::FromFile($source) }
    if ($img.Width -ne 1920 -or $img.Height -ne 1080 -or $img.RawFormat.Guid -ne [Drawing.Imaging.ImageFormat]::Png.Guid) { throw 'Gorsel 1920x1080 PNG olmali.' }
    $img.Dispose(); $img = $null
    if ($Kontrol) {
        Write-Output ('KONTROL OK: ' + $env:COMPUTERNAME + ' -> ' + $name + '. Kilit dosyasi degistirilmedi.')
        exit 0
    }
    if ([IO.File]::Exists($target)) {
        $oldAttributes = [IO.File]::GetAttributes($target)
        $backup = Join-Path $targetDir ('kilit_backup_' + [Guid]::NewGuid().ToString('N') + '.png')
        [IO.File]::Copy($target, $backup, $false)
        if ((Get-FileHash -LiteralPath $target).Hash -ne (Get-FileHash -LiteralPath $backup).Hash) { throw 'Eski gorselin yedegi dogrulanamadi; silinmedi.' }
        if (($oldAttributes -band [IO.FileAttributes]::ReadOnly) -ne 0) {
            [IO.File]::SetAttributes($target, ($oldAttributes -band (-bnot [IO.FileAttributes]::ReadOnly)))
        }
        [IO.File]::Delete($target)
        $removed = $true
    }
    [IO.File]::Move($temp, $target)
    $temp = $null
    Write-Output ('OK: ' + $env:COMPUTERNAME + ' -> ' + $name)
    exit 0
} catch {
    $failure = $_.Exception.Message
    if ($removed -and $null -ne $backup) {
        try {
            if (-not [IO.File]::Exists($target)) {
                [IO.File]::Copy($backup, $target, $false)
                [IO.File]::SetAttributes($target, $oldAttributes)
                [Console]::Error.WriteLine('Eski kilit.png yedekten geri yuklendi.')
            } else {
                [Console]::Error.WriteLine('Hedef dosya baska bir islem tarafindan olusturuldu; uzerine yazilmadi.')
            }
        } catch {
            [Console]::Error.WriteLine('Geri yukleme basarisiz. Yedek: ' + $backup + '. Hata: ' + $_.Exception.Message)
        }
    } elseif ($null -ne $oldAttributes -and [IO.File]::Exists($target)) {
        try { [IO.File]::SetAttributes($target, $oldAttributes) } catch { }
    }
    [Console]::Error.WriteLine('ISLEM BASARISIZ: ' + $failure)
    if ($null -ne $backup) { [Console]::Error.WriteLine('Eski gorsel yedegi: ' + $backup) }
    exit 20
} finally {
    if ($null -ne $img) { $img.Dispose() }
    if ($null -ne $temp -and [IO.File]::Exists($temp)) {
        try { [IO.File]::Delete($temp) } catch { }
    }
}

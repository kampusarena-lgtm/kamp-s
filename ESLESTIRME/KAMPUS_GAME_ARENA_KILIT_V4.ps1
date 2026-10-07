param([switch]$Kontrol)
$ErrorActionPreference = 'Stop'
$target = 'C:\Program Files (x86)\Pan Group\PanCafe Pro Client\upload\kilit.png'
$temp = $null
$img = $null
try {
    $rows = @(Import-Csv -LiteralPath (Join-Path $PSScriptRoot 'eski-isim-eslestirmeleri.csv') -Delimiter ';' -Encoding UTF8)
    $matches = @($rows | Where-Object { $_.'Eski bilgisayar adı' -ieq $env:COMPUTERNAME })
    if ($matches.Count -ne 1) { throw 'Bilgisayar adi listede yok veya birden fazla eslesme var.' }
    $name = $matches[0].'Görsel dosyası'
    if ([IO.Path]::GetFileName($name) -ne $name -or [IO.Path]::GetExtension($name) -ine '.jpg') { throw 'Gecersiz gorsel dosya adi.' }
    # The installation package keeps images alongside this script.
    $source = Join-Path $PSScriptRoot $name
    if (-not [IO.File]::Exists($source)) { throw 'Kaynak gorsel bulunamadi.' }
    $targetDir = [IO.Path]::GetDirectoryName($target)
    if (-not [IO.Directory]::Exists($targetDir)) { throw 'PanCafe upload klasoru bulunamadi.' }
    Add-Type -AssemblyName System.Drawing
    # Decode the selected JPEG before writing or replacing anything.
    $img = [Drawing.Image]::FromFile($source)
    if ($img.Width -ne 1920 -or $img.Height -ne 1080 -or $img.RawFormat.Guid -ne [Drawing.Imaging.ImageFormat]::Jpeg.Guid) { throw 'Kaynak gorsel 1920x1080 JPEG olmali.' }
    if (-not $Kontrol) {
        $temp = Join-Path $targetDir ('kilit_new_' + [Guid]::NewGuid().ToString('N') + '.png')
        $img.Save($temp, [Drawing.Imaging.ImageFormat]::Png)
    }
    $img.Dispose(); $img = $null
    if (-not $Kontrol) {
        $img = [Drawing.Image]::FromFile($temp)
        if ($img.Width -ne 1920 -or $img.Height -ne 1080 -or $img.RawFormat.Guid -ne [Drawing.Imaging.ImageFormat]::Png.Guid) { throw 'PNG kopyasi dogrulanamadi.' }
        $img.Dispose(); $img = $null
    }
    if ($Kontrol) {
        Write-Output ('KONTROL OK: ' + $env:COMPUTERNAME + ' -> ' + $name + '. Kilit dosyasi degistirilmedi.')
        exit 0
    }
    if ([IO.File]::Exists($target)) {
        [IO.File]::Replace($temp, $target, $null)
    } else {
        [IO.File]::Move($temp, $target)
    }
    $temp = $null
    Write-Output ('OK: ' + $env:COMPUTERNAME + ' -> ' + $name)
    exit 0
} catch {
    [Console]::Error.WriteLine('ISLEM YAPILMADI: ' + $_.Exception.Message)
    exit 20
} finally {
    if ($null -ne $img) { $img.Dispose() }
    if ($null -ne $temp -and [IO.File]::Exists($temp)) {
        try { [IO.File]::Delete($temp) } catch { }
    }
}

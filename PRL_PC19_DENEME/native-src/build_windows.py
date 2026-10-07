"""Build and smoke-check Windows apps from credential-free trial archives."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
OUT = BASE / 'Windows'
WORK = Path(os.environ.get('RUNNER_TEMP', str(HERE.parent))) / 'kampus-windows-build'


def run(args, **kwargs):
    kwargs.setdefault('timeout', 300)
    return subprocess.run(args, check=True, **kwargs)


def freeze(source, folder, name, gui=False, single=False):
    layout = ['--onefile'] if single else ['--onedir', '--contents-directory', '.']
    run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', *layout, '--name', name,
         '--windowed' if gui else '--console', '--distpath', str(folder / 'dist'),
         '--workpath', str(folder / 'build'), '--specpath', str(folder / 'spec'),
         str(folder / source)], cwd=folder)
    return folder / 'dist' / (name+'.exe' if single else name)


def resource_copy(source, target, names):
    for name in names:
        src, dest = source / name, target / name
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            shutil.copyfile(src, dest)


def bundle(folder, name, instructions):
    (folder / 'BASLA.txt').write_text(instructions, encoding='utf-8-sig')
    file = OUT / name
    with zipfile.ZipFile(file, 'w', zipfile.ZIP_DEFLATED) as zip:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                relative = path.relative_to(folder).as_posix()
                if relative.startswith('panel_private/'):
                    raise ValueError('A runtime secret folder must never enter the archive')
                zip.write(path, 'CafeMining/' + relative)
    with zipfile.ZipFile(file) as zip:
        assert zip.testzip() is None
    if file.stat().st_size >= 95_000_000:
        raise ValueError('Windows ZIP exceeds the safe GitHub file-size limit')


def main():
    if os.name != 'nt':
        raise RuntimeError('Windows applications must be compiled on Windows')
    OUT.mkdir(exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    roles = {}
    for role, archive in [('kasa', 'KASA_192-168-1-77_DENEME.zip'), ('pc19', 'PC19_BUSINESS_DENEME.zip')]:
        directory = WORK / role
        directory.mkdir(exist_ok=True)
        with zipfile.ZipFile(BASE / archive) as zip:
            zip.extractall(directory)
        source = directory / 'CafeMining'
        for path in HERE.glob('*.py'):
            if path.name != 'build_windows.py':
                shutil.copyfile(path, source / path.name)
        roles[role] = source
    panel = freeze('control_panel.py', roles['kasa'], 'Panel', gui=True)
    resource_copy(roles['kasa'], panel, ['profiles', 'settings.json'])
    # Demo self-test avoids network and private configuration creation on CI.
    run([str(panel / 'Panel.exe'), '--self-test'], timeout=30)
    record = freeze('storage_check.py', roles['kasa'], 'KayitKontrol', single=True)
    shutil.copyfile(record, panel / record.name)
    run([str(panel / 'KayitKontrol.exe'), '--help'], input='\n', text=True, timeout=30)
    (panel / 'Panel-Demo.bat').write_text('@echo off\r\n"%~dp0Panel.exe" --demo\r\n', encoding='ascii')
    trial = freeze('commission.py', roles['pc19'], 'PC19Deneme')
    resource_copy(roles['pc19'], trial, ['profiles', 'calibrations', 'references', 'device-settings'])
    run([str(trial / 'PC19Deneme.exe'), '--help'], input='\n', text=True, timeout=30)
    run([str(trial / 'PC19Deneme.exe'), '--self-test'], input='\n', text=True, timeout=30)
    bundle(panel, 'KASA_WINDOWS.zip',
        'KASA - 192.168.1.77\nPython kurulumu gerekmez. ZIP icindeki CafeMining klasorunun tamamini C:\\CafeMining olarak cikart.\n'
        'Yalniz EXE dosyasini tasima; yanindaki DLL ve klasorler de gereklidir.\n'
        'Panel.exe ac. Ilk acilista kasa ayarlari/cihaz anahtarlari yerel olarak olusur. Genel durdurmayi acik birak.\n'
        'panel_private\\agent_settings\\PC19-BUSINESS.json dosyasini yalniz PC19\'un device-settings klasorune aktar.\n'
        'TCP 8790 yalniz kafe yerel aginda ulasilabilir olmali. Paket guvenlik duvarini degistirmez.\n'
        'KayitKontrol.exe ile kaydi yeniden baslatma oncesi hazirlayip sonrasinda dogrulayabilirsin.\n'
        'Bu paket denemedir; kafe Windows/miner/OC isleyisi henuz dogrulanmadi.\n')
    bundle(trial, 'PC19_WINDOWS.zip',
        'PC19-BUSINESS - DENEME\nPython kurulumu gerekmez. CafeMining klasorunun tamamini C:\\CafeMining olarak cikart.\n'
        'Yalniz EXE dosyasini tasima; yanindaki DLL ve klasorler de gereklidir.\n'
        'Kasadan PC19-BUSINESS.json dosyasini device-settings klasorune koy.\n'
        'PC19Deneme.exe ac. 1 bos kilit, 2 musteri masaustu; 5 saniye icinde ilgili ekrani one getir.\n'
        'Bu arac mining, OC, ekran kapatma veya reset komutu vermez.\n'
        'Raporlar %LOCALAPPDATA%\\CafeMining\\diagnostics klasorundedir. Ekran goruntusu/anahtar kaydedilmez.\n'
        'Netkafem yazma onbellegi silinebilir; cihaza ozel ayar kaliciligi ayrica saglanir.\n')
    summary = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(OUT.glob('*.zip'))}
    (OUT / 'SHA256SUMS.txt').write_text(''.join(f'{digest}  {name}\n' for name, digest in summary.items()))
    print(json.dumps({'windows_build': 'passed', 'smoke_tests': 'passed', 'archives': summary}, indent=2))


if __name__ == '__main__':
    main()

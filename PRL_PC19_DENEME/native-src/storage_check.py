"""Two-phase Windows reboot proof for the panel's configured state file.

Never reboots the computer, changes safety records, or enables mining/storage flags.
Run with the panel closed. The marker is intentionally kept beside the state file.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys

from signals import read_json
from runtime_paths import application_root

ROOT = application_root(__file__)


def windows_boot_id():
    if os.name != 'nt':
        raise RuntimeError('Real reboot verification requires the Windows panel computer')
    ps = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    command = "(Get-CimInstance Win32_OperatingSystem -ErrorAction Stop).LastBootUpTime.ToUniversalTime().ToString('o')"
    result = subprocess.run([str(ps), '-NoProfile', '-NonInteractive', '-Command', command],
                            check=True, capture_output=True, text=True, timeout=15,
                            creationflags=0x08000000)
    value = result.stdout.strip()
    from datetime import datetime
    if len(value) > 64 or not value or datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo is None:
        raise ValueError('Windows boot identity could not be read')
    return value


def context(config_path, root):
    config_path = Path(config_path).resolve()
    config = read_json(config_path)
    if config.get('schema') != 1 or not isinstance(config.get('devices'), dict) or not config['devices']:
        raise ValueError('Invalid controller configuration')
    if not isinstance(config.get('state_file'), str) or not config['state_file']:
        raise ValueError('Controller state path is not configured')
    state_path = Path(config['state_file'])
    if not state_path.is_absolute():
        state_path = Path(root) / state_path
    state_path = state_path.resolve()
    state = read_json(state_path)
    if state.get('schema') != 1 or set(state.get('devices', {})) != set(config['devices']):
        raise ValueError('State file is absent/invalid or belongs to a different fleet')
    marker_path = state_path.with_name(state_path.name + '.reboot-check.json')
    digest = hashlib.sha256(state_path.read_bytes()).hexdigest()
    return config_path, state_path, marker_path, digest


def arm(config_path, root, computer, boot_id):
    config_path, state_path, marker_path, digest = context(config_path, root)
    marker = {'schema': 1, 'computer': computer, 'boot_id': boot_id,
              'config_path': str(config_path), 'state_path': str(state_path),
              'state_sha256': digest, 'nonce': secrets.token_hex(32)}
    # No overwrite: a second arm after reboot must not replace the first boot's proof.
    with marker_path.open('x', encoding='utf-8') as stream:
        json.dump(marker, stream, indent=2, allow_nan=False)
        stream.flush(); os.fsync(stream.fileno())
    return {'armed': True, 'state_path': str(state_path), 'marker_path': str(marker_path),
            'storage_automatically_enabled': False}


def verify(config_path, root, computer, boot_id):
    config_path, state_path, marker_path, digest = context(config_path, root)
    marker = read_json(marker_path)
    if (marker.get('schema') != 1 or marker.get('computer') != computer
            or marker.get('config_path') != str(config_path) or marker.get('state_path') != str(state_path)):
        raise ValueError('Reboot marker belongs to another computer/configuration/state path')
    if not isinstance(marker.get('boot_id'), str) or not marker['boot_id'] or marker['boot_id'] == boot_id:
        raise ValueError('Windows has not restarted since the first phase')
    if marker.get('state_sha256') != digest:
        raise ValueError('State changed; repeat the test with the panel closed before and after reboot')
    return {'passed': True, 'computer': computer, 'state_path': str(state_path),
            'state_survived_windows_reboot': True, 'storage_automatically_enabled': False,
            'scope': 'This configured file survived this reboot; backups and future hardware failures are not tested.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', nargs='?', choices=('arm', 'verify'))
    parser.add_argument('--config', type=Path, default=ROOT / 'panel_private/server.json')
    args = parser.parse_args()
    if args.phase is None:
        answer = input('1: Yeniden başlatmadan önce hazırla\n2: Yeniden başlattıktan sonra doğrula\nSeçim: ').strip()
        if answer not in ('1', '2'):
            parser.error('1 veya 2 gerekli')
        args.phase = 'arm' if answer == '1' else 'verify'
    try:
        boot = windows_boot_id()
        function = arm if args.phase == 'arm' else verify
        report = function(args.config, ROOT, socket.gethostname().upper(), boot)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.phase == 'arm':
            print('Paneli kapalı tut; Windows\'u normal yeniden başlat. Ardından storage_check.py verify çalıştır.')
        else:
            print('Bu dosya bu Windows yeniden başlatmasında korundu. İncelemeden sonra server.json içinde state_storage_verified=true yapılabilir.')
    except Exception as exc:
        print(f'Kalıcı kayıt denemesi: {exc}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    finally:
        if getattr(sys, 'frozen', False):
            try:
                input('Pencereyi kapatmak için Enter...')
            except EOFError:
                pass

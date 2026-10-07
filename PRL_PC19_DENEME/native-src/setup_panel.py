"""Prepare private per-device keys. Does not install or start a server/miner."""
import argparse
import json
from pathlib import Path
import secrets

from signals import read_json
from runtime_paths import application_root

ROOT = application_root(__file__)


def prepare(url, listen, port=8790, root=ROOT):
    root = Path(root)
    target = root / 'panel_private'
    if target.exists():
        raise ValueError('panel_private already exists; keep existing keys or move it intentionally')
    settings = read_json(root / 'settings.json')
    profiles = [read_json(p) for p in sorted((root / 'profiles').glob('*.json'))]
    if len(profiles) != 79:
        raise ValueError('Expected the owner\'s 79 profiles')
    target.mkdir(mode=0o700)
    enrollment = target / 'agent_settings'; enrollment.mkdir(mode=0o700)
    devices = {}
    for profile in profiles:
        pc = profile['worker']; secret = secrets.token_hex(32)
        devices[pc] = {'secret': secret, 'gpu': profile['gpu']}
        config = {**settings, 'computer': pc, 'panel': {'enabled': True, 'url': url, 'device_secret': secret, 'ca_file': ''}}
        (enrollment / f'{pc}.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    server = {'schema': 1, 'listen': listen, 'port': port,
              'certificate': '', 'private_key': '', 'state_file': 'panel_private/persistent_state.json',
              'state_storage_verified': False, 'devices': devices}
    (target / 'server.json').write_text(json.dumps(server, indent=2), encoding='utf-8')
    return target / 'server.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='Cafe controller URL')
    parser.add_argument('--listen', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8790)
    args = parser.parse_args()
    prepare(args.url, args.listen, args.port)
    print('Prepared controller configuration and 79 private agent settings. Keys were not printed.')
    print('Keep panel_private only on the controller. Give each PC only its own settings file.')


if __name__ == '__main__':
    main()

"""Observe one cafe PC and its signed panel connection; never operate mining/OC/OS."""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import sys
import time

from agent import validate_settings
from panel_protocol import PanelClient
from signals import read_json
from vision import VisionReader
from windows_runtime import Windows, gpu_state
from runtime_paths import application_root

ROOT = application_root(__file__)
LABELS = ('bos', 'musteri', 'oyun', 'siyah')


def load_trial_settings(path, worker):
    if not re.fullmatch(r'[A-Z0-9_-]{1,63}', worker):
        raise ValueError('Unexpected computer name')
    cfg = validate_settings(read_json(path))
    if cfg.get('computer') != worker or cfg['dry_run'] is not True:
        raise ValueError('Use this computer\'s own dry-run settings file')
    if cfg['session_source'] != 'vision' or cfg['panel']['enabled'] is not True:
        raise ValueError('Trial requires image analysis and the independent panel')
    return cfg


def observe(api, reader, client, nvidia_smi, label):
    interactive, idle = api.input_state()
    reader.read(api)
    vision = dict(reader.last_report)
    status = {'schema': 1, 'updated_at_epoch': time.time(), 'mining': False,
              'dry_run': True, 'trial_label': label, 'vision': vision,
              'idle_seconds': idle, 'interactive_session_ok': interactive,
              'reason': f'KURULUM DENEMESİ / {label} — mining kapalı',
              'oc_state': 'Deneme: komut verilmedi'}
    try:
        status['gpus'] = gpu_state(nvidia_smi)
    except Exception as exc:
        status['gpu_error'] = str(exc)
    result = dict(status)
    try:
        response = client.exchange(status)
        result['panel'] = {'authenticated': True,
            'desired_state': response['desired_state'],
            'emergency_stop': response['emergency_stop'],
            'persistence_available': response.get('persistence_available') is True}
    except Exception as exc:
        result['panel'] = {'authenticated': False, 'error': str(exc)}
    return result


def summarize(samples, label):
    if label not in LABELS or not samples:
        raise ValueError('Trial needs a known label and at least one sample')
    images = [sample.get('vision', {}) for sample in samples]
    matched = sum(image.get('matched') is True for image in images)
    usable = sum(image.get('usable') is True for image in images)
    connected = sum(sample.get('panel', {}).get('authenticated') is True for sample in samples)
    foregrounds = sorted({image['foreground'] for image in images
                          if isinstance(image.get('foreground'), str) and image['foreground']})
    captured = all('frame_size' in image for image in images)
    local = all(sample.get('interactive_session_ok') is True for sample in samples)
    # Negative captures must actually succeed. Capture failure is a safe runtime
    # stop, but cannot count as evidence that the two images were distinguished.
    image_pass = (captured and local and matched == len(samples) and len(foregrounds) == 1
                  if label == 'bos' else captured and local and matched == 0)
    return {'label': label, 'sample_count': len(samples), 'image_candidate_pass': image_pass,
            'matched_samples': matched, 'usable_samples': usable,
            'panel_authenticated_samples': connected,
            'panel_connection_pass': connected == len(samples),
            'foreground_candidates': foregrounds,
            'calibration_automatically_enabled': False, 'mining_started': False,
            'needs_local_calibration_review': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--settings', type=Path, default=ROOT / 'device-settings' / f'{socket.gethostname().upper()}.json')
    source.add_argument('--settings-dir', type=Path)
    parser.add_argument('--label', choices=LABELS)
    parser.add_argument('--samples', type=int, default=30)
    parser.add_argument('--delay', type=int, default=5)
    parser.add_argument('--self-test', action='store_true', help='Check packaged image libraries/resources without hardware or network')
    args = parser.parse_args()
    if args.self_test:
        from PIL import Image
        from vision import compare_images
        reader = VisionReader(ROOT, 'PC19-BUSINESS')
        if not compare_images(reader.reference, reader.reference, reader.calibration)['matched']:
            raise ValueError('Packaged reference image did not match itself')
        black = Image.new('RGB', reader.reference.size)
        if compare_images(black, reader.reference, reader.calibration)['matched']:
            raise ValueError('Black screenshot must not match the lock reference')
        if reader.calibration['verified']:
            raise ValueError('Trial calibration was unexpectedly enabled')
        print('Packaged image/runtime resources passed. No screen capture, network, GPU or miner used.')
        return
    if args.label is None:
        print('PC19 DENEME — mining, OC, ekran kapatma veya reset çalıştırılmaz.')
        print('1: Boş PanCafe kilit ekranı\n2: Müşteri masaüstü\n3: Oyun ekranı\n4: Siyah ekran')
        selected = input('Deneme türünü seç (1-4): ').strip()
        if selected not in ('1', '2', '3', '4'):
            parser.error('1–4 arasında bir seçenek gerekli')
        args.label = LABELS[int(selected)-1]
    if not 1 <= args.samples <= 300 or not 0 <= args.delay <= 30:
        parser.error('Use 1–300 samples and 0–30 seconds initial delay')
    try:
        worker = socket.gethostname().upper()
        settings_path = args.settings_dir / f'{worker}.json' if args.settings_dir else args.settings
        cfg = load_trial_settings(settings_path, worker)
        reader = VisionReader(ROOT, worker)
        client = PanelClient(cfg['panel'], worker)
        api = Windows()
        mutex = api.mutex()  # Same instance lock as the agent; no overlapping status writers.
        output = Path(os.environ['LOCALAPPDATA']) / 'CafeMining' / 'diagnostics'
        output.mkdir(parents=True, exist_ok=True)
        print(f'{args.delay} saniye içinde {args.label} ekranını öne getir. Mining komutu verilmeyecek.')
        time.sleep(args.delay)
        samples = []
        try:
            for index in range(args.samples):
                result = observe(api, reader, client, cfg['nvidia_smi'], args.label)
                samples.append(result)
                print(f"{index+1}/{args.samples}: resim={result['vision'].get('matched', False)}, "
                      f"panel={result['panel']['authenticated']}")
                if index+1 < args.samples:
                    time.sleep(2)
        finally:
            api.k.CloseHandle(mutex)
        report = {'schema': 1, 'computer': worker, 'summary': summarize(samples, args.label),
                  'samples': samples}
        name = f'{worker}-{args.label}-{time.time_ns()}.json'
        (output / name).write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        print(json.dumps(report['summary'], ensure_ascii=False, indent=2))
        print(f'Yerel tanılama kaydı: {output / name}. Ekran görüntüsü ve cihaz anahtarı kaydedilmedi.')
    except Exception as exc:
        print(f'Kurulum denemesi: {exc}', file=sys.stderr)
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

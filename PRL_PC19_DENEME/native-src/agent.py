"""CafeMining v1. Windows 11, Python 3.11+; Pillow for local screen analysis.

Live operation requires a verified image calibration (or optional bridge), a fresh economics feed,
configured payout accounts, and an approved local miner binary.
"""
import argparse
from collections import deque
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import math
import os
from pathlib import Path
import re
import socket
import sys
import time

from control import Controller, Observation, Policy
from cycle import CafeCycle, CyclePolicy
from oc_adapter import OCAdapter
from panel_protocol import PanelClient
from signals import build_miner_config, choose_coin, net_profit, number, read_json, session_state
from windows_runtime import MinerJob, Windows, gpu_state
from vision import VisionReader, validate_calibration
from runtime_paths import application_root

ROOT = application_root(__file__)


def local_path(root, value):
    path = Path(value)
    return path if path.is_absolute() else root / path


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def validate_settings(cfg):
    if cfg.get('schema') != 1 or type(cfg.get('dry_run')) is not bool or type(cfg.get('pancafe_integration_verified')) is not bool:
        raise ValueError('Invalid configuration schema or boolean flags')
    rules = {
        'idle_seconds': (60, 86400), 'session_max_age_seconds': (1, 30),
        'startup_wait_seconds': (0, 600), 'empty_wait_seconds': (0, 600),
        'monitor_off_after_mining_seconds': (1, 600),
        'poll_seconds': (0.5, 5), 'stop_temperature_c': (50, 85),
        'resume_temperature_c': (30, 75), 'cooldown_seconds': (60, 86400),
        'electricity_try_per_kwh': (0.01, 1000), 'system_overhead_watts': (0, 1000),
        'fee_fraction': (0, 0.5), 'economics_max_age_seconds': (30, 3600),
        'minimum_profit_try_per_hour': (0.01, 1000), 'switch_advantage_fraction': (0, 1),
        'minimum_switch_seconds': (60, 86400), 'max_crashes_per_hour': (1, 10),
        'restart_delay_seconds': (30, 3600)
    }
    for key, (low, high) in rules.items():
        if not low <= number(cfg[key]) <= high:
            raise ValueError(f'Invalid {key}')
    if cfg['resume_temperature_c'] >= cfg['stop_temperature_c']:
        raise ValueError('Resume temperature must be below stop temperature')
    if type(cfg['max_crashes_per_hour']) is not int:
        raise ValueError('max_crashes_per_hour must be an integer')
    for key in ('miner_exe', 'nvidia_smi', 'session_directory', 'economics_file', 'miner_exe_sha256'):
        if not isinstance(cfg[key], str):
            raise ValueError(f'Invalid {key}')
    if not isinstance(cfg['accounts'], dict):
        raise ValueError('Invalid payout accounts')
    if type(cfg.get('reboot_after_customer')) is not bool:
        raise ValueError('Invalid reboot flag')
    if cfg.get('session_source') not in ('vision', 'bridge'):
        raise ValueError('Invalid session source')
    if type(cfg.get('diskless')) is not bool:
        raise ValueError('Invalid diskless flag')
    panel = cfg.get('panel')
    if not isinstance(panel, dict) or type(panel.get('enabled')) is not bool:
        raise ValueError('Invalid panel configuration')
    for key in ('url', 'device_secret', 'ca_file'):
        if not isinstance(panel.get(key), str):
            raise ValueError(f'Invalid panel {key}')
    oc = cfg.get('oc')
    if (not isinstance(oc, dict) or type(oc.get('enabled')) is not bool
            or type(oc.get('adapter_verified')) is not bool):
        raise ValueError('Invalid OC adapter flags')
    for key in ('exe', 'exe_sha256'):
        if not isinstance(oc.get(key), str):
            raise ValueError(f'Invalid OC {key}')
    for key in ('apply_args', 'restore_args'):
        if (not isinstance(oc.get(key), list)
                or not all(isinstance(arg, str) and '\x00' not in arg for arg in oc[key])):
            raise ValueError(f'Invalid OC {key}')
    return cfg


def validate_miner(exe, expected):
    if exe.suffix.lower() != '.exe' or not exe.is_file() or not re.fullmatch('[a-fA-F0-9]{64}', expected):
        raise ValueError('Miner binary or SHA-256 is not configured')
    with exe.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual.lower() != expected.lower():
        raise ValueError('Miner binary SHA-256 does not match')


def selected_profits(cfg, profile, now):
    doc = read_json(local_path(ROOT, cfg['economics_file']))
    profits, configs = {}, {}
    for coin in ('pearl',):
        try:
            configs[coin] = build_miner_config(coin, cfg['accounts'].get(coin, {}), profile['worker'])
            profits[coin] = net_profit(doc, profile['gpu'], coin, cfg, now)
        except (KeyError, ValueError, TypeError, AttributeError):
            # Unconfigured coins cannot be selected, including during automatic switching.
            continue
    return profits, configs


def source_verified(cfg, worker):
    if cfg['session_source'] == 'bridge':
        return cfg['pancafe_integration_verified']
    try:
        doc = validate_calibration(read_json(ROOT / 'calibrations' / f'{worker}.json'))
        return bool(doc.get('computer') == worker and doc['verified'] and doc['expected_foreground_exe'])
    except Exception:
        return False


def simulation(path, cfg):
    controller = Controller(Policy(**{k: cfg[k] for k in Policy.__dataclass_fields__}))
    results = []
    for item in read_json(path):
        obs = Observation(**{**item['observation'], 'temperatures_c': tuple(item['observation']['temperatures_c'])})
        allowed, reason = controller.decide(obs, item['monotonic_seconds'])
        results.append({'scenario': item['name'], 'would_allow': allowed, 'reason': reason, 'miner_started': False})
    return results


def doctor(cfg):
    api = Windows()
    session_ok, idle = api.input_state()
    computer = socket.gethostname().upper()
    occupied, age = session_state(local_path(ROOT, cfg['session_directory']) / f'{computer}.json',
        computer, time.time(), cfg['session_max_age_seconds'])
    report = {'computer': computer, 'python': sys.version.split()[0],
              'interactive_session_ok': session_ok, 'idle_seconds': idle,
              'pancafe_occupied': occupied, 'pancafe_signal_age_seconds': age,
              'dry_run': cfg['dry_run'], 'pancafe_integration_verified': cfg['pancafe_integration_verified']}
    report['session_source'] = cfg['session_source']
    if cfg['session_source'] == 'vision':
        try:
            vision = VisionReader(ROOT, computer); vision.read(api)
            report['vision'] = vision.last_report
        except Exception as exc:
            report['vision_error'] = str(exc)
    try:
        report['gpus'] = gpu_state(local_path(ROOT, cfg['nvidia_smi']))
    except Exception as exc:
        report['gpu_error'] = str(exc)
    return report


def run(cfg, profile, live=False, once=False):
    api = Windows()
    mutex = api.mutex()
    # Trusted input/config files stay in ROOT. Writable runtime output belongs
    # to the interactive user so the miner does not need administrator rights.
    runtime = Path(os.environ['LOCALAPPDATA']) / 'CafeMining'
    state = runtime / 'state'; logs = runtime / 'logs'
    state.mkdir(parents=True, exist_ok=True); logs.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger('cafe-mining'); logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(logs / 'agent.log', maxBytes=2_000_000, backupCount=3, encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    handler.setFormatter(formatter); logger.addHandler(handler)
    console = logging.StreamHandler(); console.setFormatter(formatter); logger.addHandler(console)
    controller = Controller(Policy(**{k: cfg[k] for k in Policy.__dataclass_fields__}))
    cycle = CafeCycle(CyclePolicy(cfg['startup_wait_seconds'], cfg['empty_wait_seconds'],
                                cfg['reboot_after_customer']), time.monotonic())
    oc = OCAdapter(cfg['oc'], ROOT, validate_miner)
    monitor_off = False
    job = None; current_coin = None; started = 0.; retry_after = 0.; last_message = None
    failures = deque()
    verified = source_verified(cfg, profile['worker'])
    vision = None; vision_error = None
    if cfg['session_source'] == 'vision':
        try:
            vision = VisionReader(ROOT, profile['worker'])
        except Exception as exc:
            vision_error = str(exc)
    def read_session():
        if cfg['session_source'] == 'vision':
            return vision.read(api) if vision is not None else (None, None)
        return session_state(local_path(ROOT, cfg['session_directory']) / f"{profile['worker']}.json",
            profile['worker'], time.time(), cfg['session_max_age_seconds'])
    panel = PanelClient(cfg['panel'], profile['worker']) if cfg['panel']['enabled'] else None
    panel_ok = not cfg['panel']['enabled']; panel_reason = 'Panel disabled'
    last_restore_generation = 0
    last_panel_epoch = None
    clear_generation_applied = 0
    persisted_loaded = False
    previous_status = {'schema': 1, 'computer': profile['worker'], 'mining': False, 'reason': 'Agent starting'}
    def panel_permits_now():
        if panel is None:
            return True
        try:
            latest = panel.exchange(previous_status)
            return (latest['desired_state'] == 'auto' and not latest['emergency_stop']
                    and (not cfg['diskless'] or latest.get('persistence_available') is True))
        except Exception:
            return False
    def safety_report():
        fault = read_json(state / 'FAULT.json') if (state / 'FAULT.json').exists() else {}
        return {'thermal_latched': controller.thermal_latched,
            'cool_until_epoch': time.time()+max(0,controller.hot_until-time.monotonic()) if controller.thermal_latched else 0,
            'fault': bool(fault), 'fault_reason': fault.get('reason', ''),
            'crash_times_epoch': [time.time()-(time.monotonic()-at) for at in failures],
            'clear_generation_applied': clear_generation_applied}
    thermal_file = state / 'thermal.json'
    if thermal_file.exists():
        try:
            thermal = read_json(thermal_file)
            until = number(thermal['cool_until_epoch'])
            controller.thermal_latched = True
            controller.hot_until = time.monotonic() + max(0, until - time.time())
        except Exception:
            atomic_json(state / 'FAULT.json', {'reason': 'Thermal persistence is unreadable'})
    def stop_mining(reason):
        nonlocal job, current_coin, monitor_off
        success = True
        if job is not None:
            job.close(); job = None; current_coin = None
            logger.info('Miner stopped: %s', reason)
        try:
            oc.restore()
        except Exception as exc:
            success = False
            logger.error('OC restoration failed: %s', exc)
            atomic_json(state / 'FAULT.json', {'reason': 'OC restoration failed'})
        if monitor_off:
            try:
                api.monitor_power(False)
                monitor_off = False
            except Exception as exc:
                logger.error('Monitor wake failed: %s', exc)
        return success

    try:
        if live and not cfg['dry_run'] and verified and cfg['oc']['enabled']:
            # Recover stock settings first, including after an earlier agent crash.
            try:
                oc.restore(force=True)
            except Exception as exc:
                atomic_json(state / 'FAULT.json', {'reason': f'Initial OC restore failed: {exc}'})
        while True:
            now = time.time(); mono = time.monotonic()
            panel_ok = not cfg['panel']['enabled']
            if panel:
                try:
                    command = panel.exchange(previous_status)
                    if cfg['diskless'] and command.get('persistence_available') is not True:
                        raise ValueError('Diskless operation needs verified durable central state storage')
                    epoch = command.get('panel_epoch')
                    if epoch != last_panel_epoch:
                        last_restore_generation = 0; last_panel_epoch = epoch
                    clear_generation = command.get('clear_generation', 0)
                    if clear_generation > clear_generation_applied:
                        stop_mining('Operator cleared fault; device remains paused')
                        if (state / 'FAULT.json').exists():
                            (state / 'FAULT.json').unlink()
                        failures.clear()
                        clear_generation_applied = clear_generation
                    saved = command.get('persistent_safety', {})
                    if saved.get('fault') is True:
                        atomic_json(state / 'FAULT.json', {'reason': saved.get('fault_reason', 'Central fault latch')})
                    if saved.get('thermal_latched') is True:
                        until = number(saved['cool_until_epoch'])
                        controller.thermal_latched = True
                        controller.hot_until = max(controller.hot_until, time.monotonic()+max(0, until-time.time()))
                    if not persisted_loaded:
                        for at in saved.get('crash_times_epoch', []):
                            age = time.time()-number(at)
                            if 0 <= age <= 3600:
                                failures.append(time.monotonic()-age)
                        persisted_loaded = True
                    panel_ok = command['desired_state'] == 'auto' and not command['emergency_stop']
                    panel_reason = 'Panel permitted automatic operation' if panel_ok else 'Panel paused or emergency stop'
                    if command['restore_generation'] > last_restore_generation:
                        stop_mining('Panel requested stock GPU settings')
                        if live and not cfg['dry_run']:
                            try:
                                oc.restore(force=True)
                            except Exception:
                                atomic_json(state / 'FAULT.json', {'reason': 'Panel stock-profile restore failed'})
                        last_restore_generation = command['restore_generation']
                except Exception as exc:
                    panel_ok = False; panel_reason = f'Panel connection/authentication failed: {exc}'
                    stop_mining(panel_reason)
            # Paid-session/input check precedes the potentially blocking GPU probe.
            try:
                occupied, age = read_session()
                interactive, idle = api.input_state()
            except Exception:
                occupied, age, interactive, idle = None, None, False, None
            if not verified:
                occupied, age = None, None
            decision = cycle.observe(occupied, interactive, idle, mono)
            if (occupied is not False or not interactive or idle is None or idle < cfg['idle_seconds']
                    or not panel_ok or (ROOT / 'STOP').exists() or (state / 'FAULT.json').exists()):
                stop_mining('Customer/input/session or operator stop')
            if job is not None and not job.running():
                stop_mining('Miner unexpectedly exited')
                failures.append(mono)
                while failures and failures[0] < mono - 3600:
                    failures.popleft()
                retry_after = mono + cfg['restart_delay_seconds']
                logger.error('Miner unexpectedly exited; crash count=%d', len(failures))
                if len(failures) >= cfg['max_crashes_per_hour']:
                    atomic_json(state / 'FAULT.json', {'reason': 'Miner crash limit reached', 'time_epoch': now})
            target = None; configs = {}; profits = {}; gpus = []
            allowed = False; reason = 'Unknown state'
            try:
                if (ROOT / 'STOP').exists() or (state / 'FAULT.json').exists():
                    raise ValueError('Emergency STOP or fault latch is active')
                # Poll GPU first; read user input and paid-session status AFTER the blocking probe.
                gpus = gpu_state(local_path(ROOT, cfg['nvidia_smi']))
                if profile['gpu'].lower() not in gpus[0]['name'].lower():
                    raise ValueError('Detected GPU does not match the computer profile')
                interactive, idle = api.input_state()
                now = time.time(); mono = time.monotonic()
                occupied, age = read_session()
                obs = Observation(occupied, age, idle, tuple(g['temperature_c'] for g in gpus),
                    emergency_stop=(ROOT / 'STOP').exists(), interactive_session_ok=interactive)
                allowed, reason = controller.decide(obs, mono)
                # Refresh the cycle after the GPU probe: a customer may have arrived.
                decision = cycle.observe(occupied if verified else None,
                                         interactive, idle, mono)
                if not decision.allow_mining:
                    allowed = False; reason = f'Cafe cycle: {decision.phase}'
                if controller.thermal_latched:
                    atomic_json(thermal_file, {'cool_until_epoch': now + max(0, controller.hot_until - mono)})
                elif thermal_file.exists():
                    thermal_file.unlink()
                if not verified:
                    allowed = False; reason = 'Image calibration/session source is not verified'
                if not panel_ok:
                    allowed = False; reason = panel_reason
                if mono < retry_after:
                    allowed = False; reason = 'Waiting after a miner crash'
                if allowed:
                    profits, configs = selected_profits(cfg, profile, now)
                    target = choose_coin(profits, profile['preferred_coin'], current_coin,
                        mono - started, cfg['minimum_profit_try_per_hour'], cfg['switch_advantage_fraction'],
                        cfg['minimum_switch_seconds'])
                    if target is None:
                        allowed = False; reason = 'No configured coin with sufficient estimated net income'
            except Exception as exc:
                allowed = False; reason = f'Blocked: {exc}'
            execute = live and not cfg['dry_run']
            if job is not None and (not allowed or current_coin != target or not execute):
                stop_mining(reason)
            reboot_accepted = False
            if (decision.request_reboot and execute and verified and panel_ok
                    and not (ROOT / 'STOP').exists() and not (state / 'FAULT.json').exists()):
                if stop_mining('Customer departed: preparing reboot'):
                    try:
                        # OC restoration can take time. Recheck before committing.
                        if not panel_permits_now():
                            raise ValueError('Panel no longer permits reboot')
                        occupied, age = read_session()
                        interactive, idle = api.input_state()
                        recheck = cycle.observe(occupied, interactive, idle, time.monotonic())
                        if recheck.request_reboot and not (ROOT / 'STOP').exists():
                            if panel:
                                saved_before_reboot = panel.exchange({'schema': 1, 'computer': profile['worker'],
                                    'mining': False, 'safety': safety_report(), 'gpus': gpus})
                                if (saved_before_reboot['emergency_stop'] or saved_before_reboot['desired_state'] != 'auto'
                                        or cfg['diskless'] and saved_before_reboot.get('persistence_available') is not True):
                                    raise ValueError('Controller did not permit/commit the reboot')
                                occupied, age = read_session()
                                interactive, idle = api.input_state()
                                if not cycle.observe(occupied, interactive, idle, time.monotonic()).request_reboot:
                                    raise ValueError('Customer/input changed while committing reboot safety')
                            api.request_reboot()
                            cycle.mark_reboot_requested()
                            reboot_accepted = True
                            reason = 'Windows reboot requested after verified customer departure'
                            atomic_json(state / 'reboot-request.json', {'time_epoch': time.time(), 'reason': reason})
                    except Exception as exc:
                        reason = f'Reboot failed: {exc}'
                        atomic_json(state / 'FAULT.json', {'reason': reason})
            if allowed and execute and job is None:
                try:
                    # Hash checked at every start, so a replaced binary is not trusted by an earlier check.
                    exe = local_path(ROOT, cfg['miner_exe']).resolve()
                    validate_miner(exe, cfg['miner_exe_sha256'])
                    # Recheck paid-session/input after reading the potentially large binary.
                    occupied, age = read_session()
                    interactive, idle = api.input_state()
                    recheck = Observation(occupied, age, idle, tuple(g['temperature_c'] for g in gpus),
                        emergency_stop=(ROOT / 'STOP').exists(), interactive_session_ok=interactive)
                    still_allowed, recheck_reason = controller.decide(recheck, time.monotonic())
                    if not still_allowed:
                        raise ValueError(f'Pre-launch safety check: {recheck_reason}')
                    if not cycle.observe(occupied, interactive, idle, time.monotonic()).allow_mining:
                        raise ValueError('Pre-launch safety check: cafe cycle is waiting')
                    miner_config = state / 'generated-miner-config.json'
                    atomic_json(miner_config, configs[target])
                    # Separate arguments; no shell and no batch-file command interpolation.
                    args = ['--config', str(miner_config.resolve()), '--nvidia', '--cpu', '0',
                            '--amd', '0', '--intel', '0', '--igpu', '0']
                    oc.apply()
                    if not panel_permits_now():
                        raise ValueError('Pre-launch safety check: panel stop or connection loss')
                    # Applying an OC profile can take time too. Do not start a
                    # miner using a paid-session check from before that command.
                    occupied, age = read_session()
                    interactive, idle = api.input_state()
                    check = Observation(occupied, age, idle, tuple(g['temperature_c'] for g in gpus),
                        emergency_stop=(ROOT / 'STOP').exists(), interactive_session_ok=interactive)
                    if not controller.decide(check, time.monotonic())[0]:
                        raise ValueError('Pre-launch safety check: customer/input changed during OC setup')
                    job = MinerJob(api, exe, args, logs / f'miner-{int(now)}.log')
                    current_coin = target; started = time.monotonic()
                    logger.info('Miner started: coin=%s', target)
                except Exception as exc:
                    stop_mining('Startup aborted')
                    allowed = False; reason = f'Miner startup failed: {exc}'
                    # A customer arriving during preparation is a normal stop.
                    # Actual startup errors latch rather than retrying indefinitely.
                    if not str(exc).startswith('Pre-launch safety check:'):
                        atomic_json(state / 'FAULT.json', {'reason': 'Miner startup failed', 'time_epoch': now})
            if (job is not None and allowed and execute and not monitor_off
                    and time.monotonic() - started >= cfg['monitor_off_after_mining_seconds']):
                try:
                    # Screen-off is permitted only while the miner is running
                    # and the current customer/input checks still pass.
                    if not panel_permits_now():
                        raise ValueError('Panel no longer permits screen-off')
                    occupied, age = read_session()
                    interactive, idle = api.input_state()
                    check = Observation(occupied, age, idle, tuple(g['temperature_c'] for g in gpus),
                        emergency_stop=(ROOT / 'STOP').exists(), interactive_session_ok=interactive)
                    if controller.decide(check, time.monotonic())[0]:
                        # An API timeout can occur after the command was sent.
                        # Mark the attempt first so error cleanup still wakes it.
                        monitor_off = True
                        api.monitor_power(True)
                    else:
                        allowed = False; reason = 'Customer/input changed before screen-off'
                        stop_mining(reason)
                except Exception as exc:
                    allowed = False; reason = f'Screen-off check failed: {exc}'
                    stop_mining(reason)
            status = {'schema': 1, 'computer': profile['worker'], 'updated_at_epoch': now,
                'mode': 'live' if execute else 'dry_run', 'mining': job is not None,
                'would_allow': allowed, 'selected_coin': target, 'reason': reason,
                'estimated_profit_try_per_hour': profits, 'gpus': gpus,
                'cafe_phase': decision.phase, 'wait_remaining_seconds': decision.remaining_seconds,
                'monitor_off_command_sent': monitor_off, 'reboot_requested': reboot_accepted,
                'would_request_reboot': decision.request_reboot}
            status['session_source'] = cfg['session_source']
            status['vision'] = (vision.last_report if vision else {'usable': False, 'reason': vision_error}) if cfg['session_source'] == 'vision' else {}
            status['oc_state'] = 'mining' if oc.dirty else 'stock' if cfg['oc']['enabled'] and cfg['oc']['adapter_verified'] else 'not_configured'
            status['panel'] = {'enabled': cfg['panel']['enabled'], 'operation_allowed': panel_ok, 'reason': panel_reason}
            status['safety'] = safety_report()
            if panel:
                try:
                    committed = panel.exchange(status)
                    if (committed['desired_state'] != 'auto' or committed['emergency_stop']
                            or cfg['diskless'] and committed.get('persistence_available') is not True):
                        stop_mining('Panel stopped operation during state commit')
                        status['mining'] = False
                except Exception as exc:
                    stop_mining('Current safety state could not be committed to the controller')
                    status['mining'] = False; status['would_allow'] = False
                    status['reason'] = f'Central state commit failed: {exc}'
            previous_status = status
            atomic_json(state / 'status.json', status)
            message = (status['mode'], status['mining'], allowed, target, reason)
            if message != last_message:
                logger.info('mode=%s mining=%s allowed=%s coin=%s reason=%s', *message)
                last_message = message
            if once or reboot_accepted:
                break
            time.sleep(cfg['poll_seconds'])
    except KeyboardInterrupt:
        logger.info('Operator stopped the agent')
    finally:
        stop_mining('Agent stopped')
        api.k.CloseHandle(mutex)
        atomic_json(state / 'status.json', {'schema': 1, 'computer': profile['worker'],
            'updated_at_epoch': time.time(), 'mining': False, 'reason': 'Agent stopped'})
        handler.close(); logger.removeHandler(handler); logger.removeHandler(console)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings', type=Path, default=ROOT / 'settings.json')
    parser.add_argument('--settings-dir', type=Path, help='Read this host\'s settings from a protected shared configuration directory')
    parser.add_argument('--live', action='store_true', help='Run live only if dry_run=false and ALL checks pass')
    parser.add_argument('--once', action='store_true', help='Observe one polling cycle, then stop')
    parser.add_argument('--doctor', action='store_true', help='Read-only Windows hardware and session diagnostics')
    parser.add_argument('--simulate', type=Path, help='Evaluate labelled sample observations without Windows or a miner')
    args = parser.parse_args()
    try:
        worker = socket.gethostname().upper()
        cfg = validate_settings(read_json(args.settings_dir / f'{worker}.json' if args.settings_dir else args.settings))
        if cfg.get('computer', worker) != worker:
            raise ValueError('This settings file belongs to another computer')
        if args.simulate:
            print(json.dumps(simulation(args.simulate, cfg), indent=2, ensure_ascii=False)); return
        if args.doctor:
            print(json.dumps(doctor(cfg), indent=2, ensure_ascii=False)); return
        if not re.fullmatch(r'[A-Z0-9_-]{1,63}', worker):
            raise ValueError('Unexpected computer name')
        profile = read_json(ROOT / 'profiles' / f'{worker}.json')
        if profile.get('worker') != worker or profile.get('preferred_coin') != 'pearl':
            raise ValueError('Computer profile does not match this host')
        if args.live and cfg['dry_run']:
            raise ValueError('settings.json still has dry_run=true; no miner was started')
        if args.live and cfg['diskless'] and not cfg['panel']['enabled']:
            raise ValueError('Diskless live operation requires the independent controller and durable central state')
        if args.live and not source_verified(cfg, worker):
            raise ValueError('Image calibration/session source is not verified; no miner was started')
        run(cfg, profile, args.live, args.once)
    except Exception as exc:
        print(f'CafeMining: {exc}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

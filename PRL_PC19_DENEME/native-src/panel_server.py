"""Agent-only HTTP API. Operator controls exist only in the local desktop panel."""
from collections import OrderedDict
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import re
import secrets
import os
from pathlib import Path
import threading
import time

from panel_protocol import encode, request_signature, response_signature


class PanelStore:
    def __init__(self, devices, state_file=None, storage_verified=False):
        self.devices = devices
        self.lock = threading.RLock()
        self.emergency_stop = True
        self.epoch = secrets.token_hex(16)
        self.status = {}
        self.commands = {pc: {'desired_state': 'paused', 'restore_generation': 0, 'clear_generation': 0} for pc in devices}
        self.nonces = {pc: OrderedDict() for pc in devices}
        self.state_file = Path(state_file) if state_file else None
        self.storage_verified = storage_verified and self.state_file is not None
        self.safety = {pc: {'thermal_latched': False, 'cool_until_epoch': 0, 'fault': False,
                            'fault_reason': '', 'crash_times_epoch': []} for pc in devices}
        if self.state_file and self.state_file.exists():
            from signals import read_json
            doc = read_json(self.state_file)
            if doc.get('schema') != 1 or set(doc.get('devices', {})) != set(devices):
                raise ValueError('Central state is invalid or belongs to another fleet')
            for pc, saved in doc['devices'].items():
                safety = saved['safety']
                if (type(safety.get('fault')) is not bool or type(safety.get('thermal_latched')) is not bool
                        or type(safety.get('cool_until_epoch')) not in (int, float)
                        or not math.isfinite(safety['cool_until_epoch'])
                        or not isinstance(safety.get('crash_times_epoch'), list)
                        or not all(type(t) in (int, float) and math.isfinite(t) for t in safety['crash_times_epoch'])):
                    raise ValueError('Central safety record is invalid')
                self.safety[pc] = safety
                for key in ('clear_generation', 'restore_generation'):
                    value = saved.get(key, 0)
                    if type(value) is not int or value < 0:
                        raise ValueError('Central command generation is invalid')
                    self.commands[pc][key] = value
        if self.state_file:
            self._save()

    def _save(self):
        if self.state_file is None:
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        doc = {'schema': 1, 'devices': {pc: {'safety': state,
            'clear_generation': self.commands[pc]['clear_generation'],
            'restore_generation': self.commands[pc]['restore_generation']} for pc, state in self.safety.items()}}
        temporary = self.state_file.with_name(self.state_file.name + '.tmp')
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(doc, stream, ensure_ascii=False, allow_nan=False)
            stream.flush(); os.fsync(stream.fileno())
        temporary.replace(self.state_file)

    def _merge_safety(self, pc, status, now):
        reported = status.get('safety', {})
        if not isinstance(reported, dict):
            raise ValueError('Invalid safety report')
        state = self.safety[pc]
        if reported.get('thermal_latched') is True:
            until = reported.get('cool_until_epoch')
            if type(until) not in (float, int) or not math.isfinite(until) or not 0 <= until <= now+86460:
                raise ValueError('Invalid thermal deadline')
            state['thermal_latched'] = True
            state['cool_until_epoch'] = max(state['cool_until_epoch'], until)
        elif reported.get('thermal_latched') is False and state['thermal_latched']:
            gpus = status.get('gpus')
            if isinstance(gpus, list) and len(gpus) == 1 and isinstance(gpus[0], dict):
                temp = gpus[0].get('temperature_c')
                if (type(temp) in (int, float) and math.isfinite(temp) and 0 <= temp <= 60
                        and now >= state['cool_until_epoch']):
                    state['thermal_latched'] = False
        acknowledged = reported.get('clear_generation_applied', 0)
        if type(acknowledged) is not int:
            raise ValueError('Invalid fault-clear acknowledgement')
        if acknowledged >= self.commands[pc]['clear_generation']:
            if reported.get('fault') is True:
                state['fault'] = True; state['fault_reason'] = str(reported.get('fault_reason', 'Agent fault'))[:200]
            crashes = reported.get('crash_times_epoch', [])
            if not isinstance(crashes, list) or len(crashes) > 20:
                raise ValueError('Invalid crash history')
            current = [t for t in state['crash_times_epoch'] if now-3600 <= t <= now+30]
            for at in crashes:
                if type(at) not in (float, int) or not math.isfinite(at):
                    raise ValueError('Invalid crash timestamp')
                if now-3600 <= at <= now+30 and not any(abs(at-old) < 2 for old in current):
                    current.append(at)
            state['crash_times_epoch'] = sorted(current)[-20:]
            if len(current) >= 3:
                state['fault'] = True; state['fault_reason'] = 'Miner crash limit reached'

    def flush_safety(self, pc, status, now):
        with self.lock:
            self._merge_safety(pc, status, now); self._save()

    def authenticate(self, pc, path, stamp, nonce, signature, body, now):
        if pc not in self.devices or not re.fullmatch('[0-9a-f]{32}', nonce):
            raise ValueError('Authentication failed')
        try:
            age = now - int(stamp)
        except (ValueError, TypeError):
            raise ValueError('Authentication failed')
        if not -30 <= age <= 30:
            raise ValueError('Request expired')
        secret = self.devices[pc]['secret']
        expected = request_signature(secret, path, stamp, nonce, body)
        if not hmac.compare_digest(signature, expected):
            raise ValueError('Authentication failed')
        with self.lock:
            seen = self.nonces[pc]
            for old, at in list(seen.items()):
                if at < now - 61:
                    del seen[old]
            if nonce in seen:
                raise ValueError('Request replayed')
            if len(seen) >= 1000:
                raise ValueError('Device request limit exceeded')
            seen[nonce] = now
        return secret

    def heartbeat(self, pc, status, now):
        if not isinstance(status, dict):
            raise ValueError('Status must be an object')
        with self.lock:
            self._merge_safety(pc, status, now)
            self._save()
            self.status[pc] = {'received_at': now, 'data': status}
            return {'schema': 1, 'computer': pc, 'panel_epoch': self.epoch,
                    'emergency_stop': self.emergency_stop, 'persistence_available': self.storage_verified,
                    'persistent_safety': dict(self.safety[pc]), **self.commands[pc]}

    def command(self, pcs, action):
        with self.lock:
            if action == 'emergency':
                self.emergency_stop = True
                for command in self.commands.values():
                    command['desired_state'] = 'paused'
            elif action == 'release':
                self.emergency_stop = False
            elif action in ('auto', 'paused', 'stock', 'clear_fault'):
                for pc in pcs:
                    if pc not in self.commands:
                        raise ValueError('Unknown device')
                    self.commands[pc]['desired_state'] = 'auto' if action == 'auto' else 'paused'
                    if action == 'stock':
                        self.commands[pc]['restore_generation'] += 1
                    elif action == 'clear_fault':
                        self.commands[pc]['clear_generation'] += 1
                        self.safety[pc]['fault'] = False
                        self.safety[pc]['fault_reason'] = ''
                        self.safety[pc]['crash_times_epoch'] = []
            else:
                raise ValueError('Unknown panel action')
            self._save()

    def snapshot(self):
        with self.lock:
            return {pc: {'command': dict(self.commands[pc]),
                         'heartbeat': self.status.get(pc)} for pc in self.devices}


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def log_message(self, *args):
            pass

        def do_POST(self):
            match = re.fullmatch(r'/api/v1/([A-Z0-9_-]{1,63})/heartbeat', self.path)
            if not match:
                self.send_error(404); return
            pc = match.group(1)
            try:
                size = int(self.headers.get('Content-Length', '-1'))
                if not 0 < size <= 128000 or self.headers.get('Transfer-Encoding'):
                    raise ValueError('Invalid request size')
                body = self.rfile.read(size)
                if len(body) != size:
                    raise ValueError('Incomplete request')
                nonce = self.headers.get('X-Cafe-Nonce', '')
                secret = store.authenticate(pc, self.path, self.headers.get('X-Cafe-Time', ''), nonce,
                    self.headers.get('X-Cafe-Signature', ''), body, time.time())
                doc = json.loads(body, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
                if doc.get('schema') != 1 or doc.get('computer') != pc:
                    raise ValueError('Invalid device heartbeat')
                result = store.heartbeat(pc, doc.get('status'), time.time())
                raw = encode(result)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('X-Cafe-Signature', response_signature(secret, nonce, raw))
                self.end_headers(); self.wfile.write(raw)
            except (ValueError, TypeError, KeyError, AttributeError, TimeoutError, OSError):
                self.send_error(403, 'Heartbeat rejected')
    return Handler


def serve(store, host, port, certificate='', private_key=''):
    server = ThreadingHTTPServer((host, port), make_handler(store))
    server.daemon_threads = True
    if certificate or private_key:
        import ssl
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, private_key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server

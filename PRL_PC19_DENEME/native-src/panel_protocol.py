"""Authenticated LAN heartbeats. Secrets never travel in request headers.

HMAC protects commands/integrity/replays. Use HTTPS for confidentiality as well.
"""
import hashlib
import hmac
import json
import secrets
import ssl
import time
import urllib.request


def encode(doc):
    return json.dumps(doc, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def request_signature(secret, path, stamp, nonce, body):
    message = b'POST\n' + path.encode() + b'\n' + stamp.encode() + b'\n' + nonce.encode() + b'\n' + body
    return hmac.new(bytes.fromhex(secret), message, hashlib.sha256).hexdigest()


def response_signature(secret, nonce, body):
    return hmac.new(bytes.fromhex(secret), b'RESPONSE\n' + nonce.encode() + b'\n' + body, hashlib.sha256).hexdigest()


class PanelClient:
    def __init__(self, settings, worker):
        self.settings, self.worker = settings, worker
        if not settings['url'].startswith(('http://', 'https://')):
            raise ValueError('Panel URL must be HTTP(S)')
        from urllib.parse import urlsplit
        parsed = urlsplit(settings['url'])
        if (not parsed.hostname or parsed.username or parsed.password or parsed.query
                or parsed.fragment or parsed.path not in ('', '/')):
            raise ValueError('Invalid panel base URL')
        if len(bytes.fromhex(settings['device_secret'])) != 32:
            raise ValueError('Panel device key is not configured')
        # Ignore inherited proxy variables for local cafe control traffic.
        handlers = [urllib.request.ProxyHandler({})]
        if parsed.scheme == 'https':
            context = ssl.create_default_context(cafile=settings.get('ca_file') or None)
            handlers.append(urllib.request.HTTPSHandler(context=context))
        self.opener = urllib.request.build_opener(*handlers)

    def exchange(self, status):
        path = f'/api/v1/{self.worker}/heartbeat'
        body = encode({'schema': 1, 'computer': self.worker, 'status': status})
        stamp, nonce = str(int(time.time())), secrets.token_hex(16)
        req = urllib.request.Request(self.settings['url'].rstrip('/') + path, data=body,
            headers={'Content-Type': 'application/json', 'X-Cafe-Time': stamp, 'X-Cafe-Nonce': nonce,
                     'X-Cafe-Signature': request_signature(self.settings['device_secret'], path, stamp, nonce, body)},
            method='POST')
        with self.opener.open(req, timeout=1.5) as response:
            raw = response.read(128001)
            signature = response.headers.get('X-Cafe-Signature', '')
        if len(raw) > 128000 or not hmac.compare_digest(signature,
                response_signature(self.settings['device_secret'], nonce, raw)):
            raise ValueError('Invalid panel response signature or size')
        doc = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        if (doc.get('schema') != 1 or doc.get('computer') != self.worker
                or doc.get('desired_state') not in ('auto', 'paused')
                or type(doc.get('emergency_stop')) is not bool
                or not isinstance(doc.get('panel_epoch'), str)
                or type(doc.get('restore_generation')) is not int):
            raise ValueError('Invalid panel control response')
        return doc

"""Fresh, host-specific input files for a VERIFIED PanCafe bridge and price feed.

The JSON contract is ours, not an undocumented PanCafe API.
"""
import json
import math
import re
from pathlib import Path
from urllib.parse import urlsplit


def read_json(path: Path):
    if path.stat().st_size > 256_000:
        raise ValueError('Signal file too large')
    with path.open(encoding='utf-8-sig') as stream:
        return json.load(stream, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Expected finite number')
    return float(value)


def fresh_age(doc, now, max_age):
    age = now - number(doc.get('updated_at_epoch'))
    if not 0 <= age <= max_age:
        raise ValueError('Stale or future-dated signal')
    return age


def session_state(path, computer, now, max_age):
    try:
        doc = read_json(Path(path))
        if doc.get('schema') != 1 or doc.get('computer', '').upper() != computer.upper():
            raise ValueError('Wrong schema or computer')
        if doc.get('connected') is not True or type(doc.get('occupied')) is not bool:
            raise ValueError('Disconnected or unknown session')
        age = fresh_age(doc, now, max_age)
        return doc['occupied'], age
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        return None, None


def net_profit(economics, gpu, coin, settings, now):
    if economics.get('schema') != 1 or economics.get('source_verified') is not True:
        raise ValueError('Economics source is not verified')
    fresh_age(economics, now, settings['economics_max_age_seconds'])
    fx = number(economics['usd_try'])
    row = economics['gpus'][gpu][coin]
    revenue = number(row['revenue_usd_per_24h'])
    power = number(row['gpu_watts'])
    if fx <= 0 or revenue < 0 or power < 0:
        raise ValueError('Invalid economics input')
    overhead = number(settings['system_overhead_watts'])
    fee = number(settings['fee_fraction'])
    tariff = number(settings['electricity_try_per_kwh'])
    return revenue * fx * (1 - fee) / 24 - (power + overhead) / 1000 * tariff


def choose_coin(profits, preferred, current=None, runtime_seconds=0,
                threshold=0.5, advantage=0.1, min_runtime=1800):
    viable = {c: v for c, v in profits.items() if math.isfinite(v) and v >= threshold}
    if not viable:
        return None
    best = max(viable, key=lambda coin: (viable[coin], coin == preferred))
    if current in viable and (runtime_seconds < min_runtime or viable[best] < viable[current] * (1 + advantage)):
        return current
    return best


def build_miner_config(coin, account, worker):
    if coin not in ('pearl', 'quantus') or not re.fullmatch(r'[A-Za-z0-9_-]{1,63}', worker):
        raise ValueError('Invalid coin or worker')
    pool, wallet = account.get('pool', ''), account.get('wallet', '')
    if not isinstance(pool, str) or not isinstance(wallet, str) or not wallet or re.search(r'\s', wallet):
        raise ValueError('Pool or public wallet/account is missing')
    parsed = urlsplit(pool)
    if parsed.scheme not in ('stratum+tcp', 'stratum+ssl') or not parsed.hostname or not parsed.port:
        raise ValueError('Pool must be a Stratum endpoint with a port')
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise ValueError('Unsupported pool URL')
    fmt = account.get('worker_format', 'separate')
    if fmt == 'slash':
        login, pool_worker = f'{wallet}/{worker}', ''
    elif fmt == 'dot':
        login, pool_worker = f'{wallet}.{worker}', ''
    elif fmt == 'separate':
        login, pool_worker = wallet, worker
    else:
        raise ValueError('Unknown pool worker format')
    return {
        'pool': 0,
        'pools': [{'url': pool, 'wallet': login, 'worker': pool_worker, 'algo': coin}],
        'device_types': {'nvidia': True, 'amd': False, 'intel': False, 'cpu': False},
        'http_address': '127.0.0.1',
        'http_enabled': False
    }

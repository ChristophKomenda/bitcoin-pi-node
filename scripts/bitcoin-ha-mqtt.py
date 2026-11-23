#!/usr/bin/env python3
"""Read-only Bitcoin Core telemetry for Home Assistant MQTT Discovery.

Optional host-side publisher; does not publish RPC or manage Bitcoin Core lifecycle.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PREFIX = os.environ.get('BITCOIN_HA_PREFIX', 'bitcoin_pi_node').strip('/')
DEVICE_ID = os.environ.get('BITCOIN_HA_DEVICE_ID', 'bitcoin_pi_node')
CONTAINER = os.environ.get('BITCOIN_CONTAINER', 'bitcoin')
STATE_TOPIC = f'{PREFIX}/state'
AVAILABILITY_TOPIC = f'{PREFIX}/availability'

# Original names and identifiers deliberately preserved for existing HA entities.
SENSORS = {
    'blocks': ('Block Height', 'blocks', None, None),
    'headers': ('Header Height', 'headers', None, None),
    'verification_progress': ('Verification Progress', 'verification_progress', '%', 'measurement'),
    'peers': ('Connected Peers', 'peers', None, 'measurement'),
    'inbound': ('Inbound Peers', 'inbound', None, 'measurement'),
    'outbound': ('Outbound Peers', 'outbound', None, 'measurement'),
    'disk_gib': ('Blockchain Data Size', 'disk_gib', 'GiB', 'measurement'),
    'prune_height': ('Prune Height', 'prune_height', None, None),
    'chain': ('Chain', 'chain', None, None),
    'version': ('Bitcoin Core Version', 'version', None, None),
    'uptime_seconds': ('Node Uptime', 'uptime_seconds', 's', 'measurement'),
    'bytes_received_gib': ('Network Received', 'bytes_received_gib', 'GiB', 'total_increasing'),
    'bytes_sent_gib': ('Network Sent', 'bytes_sent_gib', 'GiB', 'total_increasing'),
    'storage_free_gib': ('Storage Free', 'storage_free_gib', 'GiB', 'measurement'),
    'sync_stalled_minutes': ('Sync Stall Duration', 'sync_stalled_minutes', 'min', 'measurement'),
}
BINARY_SENSORS = {
    'initial_download': ('Initial Block Download', 'initial_download'),
    'pruned': ('Pruning Enabled', 'pruned'),
    'synchronized': ('Synchronized', 'synchronized'),
    'low_storage': ('Low Storage', 'low_storage'),
    'no_peers': ('No Peers', 'no_peers'),
    'sync_stalled': ('Sync Stalled', 'sync_stalled'),
}


def rpc(method):
    result = subprocess.run(
        ['docker', 'exec', CONTAINER, 'bitcoin-cli', '-datadir=/home/bitcoin/.bitcoin', method],
        capture_output=True, text=True, check=True, timeout=20,
    )
    return json.loads(result.stdout)


def positive_int_env(name, default):
    value = int(os.environ.get(name, str(default)))
    if value <= 0:
        raise ValueError(f'{name} must be a positive integer')
    return value


def state_path():
    return Path(os.environ.get('BITCOIN_HA_CACHE_FILE', str(Path.home() / '.cache/bitcoin-pi-node/ha-telemetry.json')))


def read_cache(path):
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(raw, dict):
            return {}
        return raw
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def write_cache(path, data):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    try:
        fd = os.open(str(temp), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def storage_free_gib():
    """Monitor actual configured Bitcoin storage, not an absent mount/fallback root disk."""
    location = Path(os.environ.get('BITCOIN_DATA_DIR', '/srv/bitcoin'))
    if not location.is_mount():
        return None
    stat = os.statvfs(location)
    return round(stat.f_bavail * stat.f_frsize / (1024 ** 3), 3)


def build_snapshot(chain, net, totals, uptime, free_gib, old_cache, now):
    blocks, headers = int(chain['blocks']), int(chain['headers'])
    ibd = bool(chain['initialblockdownload'])
    synchronized = not ibd and blocks > 0 and 0 <= headers - blocks <= 1
    state = {
        'blocks': blocks, 'headers': headers,
        'verification_progress': round(float(chain['verificationprogress']) * 100, 4),
        'peers': int(net.get('connections', 0)),
        'inbound': int(net.get('connections_in', 0)),
        'outbound': int(net.get('connections_out', 0)),
        'disk_gib': round(int(chain.get('size_on_disk', 0)) / 1024 ** 3, 3),
        'prune_height': int(chain.get('pruneheight', 0)),
        'chain': str(chain['chain']),
        'version': str(net.get('subversion', 'unknown')),
        'initial_download': ibd,
        'pruned': bool(chain.get('pruned', False)),
        'synchronized': synchronized,
        'uptime_seconds': int(uptime),
        'bytes_received_gib': round(int(totals['totalbytesrecv']) / 1024 ** 3, 4),
        'bytes_sent_gib': round(int(totals['totalbytessent']) / 1024 ** 3, 4),
        'no_peers': int(net.get('connections', 0)) == 0,
    }
    state['storage_free_gib'] = free_gib
    state['low_storage'] = (free_gib < positive_int_env('BITCOIN_HA_STORAGE_WARN_GIB', 5)
                            if free_gib is not None else None)

    # Stall alarms only apply during initial sync. Progress means validated block
    # height increased; known headers may keep advancing while validation is stuck.
    previous_height = old_cache.get('blocks')
    last_advance = old_cache.get('last_advance', now)
    try:
        last_advance = float(last_advance)
    except (TypeError, ValueError):
        last_advance = now
    if previous_height != blocks or now < last_advance or not ibd:
        last_advance = now
    duration = max(0, (now - last_advance) / 60) if ibd else 0
    state['sync_stalled_minutes'] = round(duration, 1)
    state['sync_stalled'] = ibd and duration >= positive_int_env('BITCOIN_HA_STALL_WARN_MINUTES', 30)
    cache = {'blocks': blocks, 'last_advance': last_advance}
    return state, cache


def snapshot():
    chain = rpc('getblockchaininfo')
    net = rpc('getnetworkinfo')
    totals = rpc('getnettotals')
    uptime = rpc('uptime')
    free = storage_free_gib()
    path = state_path()
    state, cache = build_snapshot(chain, net, totals, uptime, free, read_cache(path), time.time())
    write_cache(path, cache)
    return state


def configs():
    discovery_prefix = os.environ.get('MQTT_DISCOVERY_PREFIX', 'homeassistant').strip('/')
    device = {'identifiers': [DEVICE_ID], 'name': 'Bitcoin Pi Node',
              'manufacturer': 'Community', 'model': 'Bitcoin Core (Docker)'}
    # Missing periodic publications make sensors unavailable even if broker
    # retains the previous online status. Timer period default is ~60 seconds.
    expiry = positive_int_env('BITCOIN_HA_EXPIRE_AFTER', 300)
    for key, (name, field, unit, state_class) in SENSORS.items():
        config = {'name': name, 'unique_id': f'{DEVICE_ID}_{key}',
                  'state_topic': STATE_TOPIC,
                  'value_template': '{{ value_json.' + field + ' }}',
                  'availability_topic': AVAILABILITY_TOPIC,
                  'expire_after': expiry,
                  'device': device}
        if unit:
            config['unit_of_measurement'] = unit
        if state_class:
            config['state_class'] = state_class
        if key == 'uptime_seconds':
            config['device_class'] = 'duration'
        yield f'{discovery_prefix}/sensor/{DEVICE_ID}/{key}/config', config
    for key, (name, field) in BINARY_SENSORS.items():
        template = ("{{ 'ON' if value_json.low_storage == true else 'OFF' if value_json.low_storage == false else 'unknown' }}"
                    if key == 'low_storage' else
                    "{{ 'ON' if value_json." + field + " else 'OFF' }}")
        config = {'name': name, 'unique_id': f'{DEVICE_ID}_{key}',
                  'state_topic': STATE_TOPIC,
                  'value_template': template,
                  'payload_on': 'ON', 'payload_off': 'OFF',
                  'availability_topic': AVAILABILITY_TOPIC,
                  'expire_after': expiry,
                  'device': device}
        if key in {'low_storage', 'no_peers', 'sync_stalled'}:
            config['device_class'] = 'problem'
        yield f'{discovery_prefix}/binary_sensor/{DEVICE_ID}/{key}/config', config


def load_password():
    filename = os.environ.get('MQTT_PASSWORD_FILE', '').strip()
    if filename:
        path = Path(filename)
        if path.stat().st_mode & 0o077:
            raise ValueError('MQTT_PASSWORD_FILE must not be accessible by group/others (chmod 600)')
        return path.read_text(encoding='utf-8').strip()
    return None


def send(client, topic, payload):
    info = client.publish(topic, payload, qos=1, retain=True)
    info.wait_for_publish(timeout=10)
    if not info.is_published():
        raise RuntimeError(f'MQTT publication failed: {topic}')


def main():
    import paho.mqtt.client as mqtt
    if not PREFIX or not DEVICE_ID:
        raise ValueError('BITCOIN_HA_PREFIX and BITCOIN_HA_DEVICE_ID cannot be blank')
    host = os.environ.get('MQTT_HOST')
    if not host:
        raise ValueError('MQTT_HOST is required')
    port = int(os.environ.get('MQTT_PORT', '1883'))
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f'{DEVICE_ID}_publisher')
    username = os.environ.get('MQTT_USERNAME', '')
    password = load_password()
    if username:
        client.username_pw_set(username, password)
    if os.environ.get('MQTT_TLS', 'false').lower() == 'true':
        client.tls_set()
    client.connect(host, port, keepalive=30)
    client.loop_start()
    try:
        for topic, config in configs():
            send(client, topic, json.dumps(config, separators=(',', ':')))
        try:
            state = snapshot()
        except (subprocess.SubprocessError, ValueError, KeyError, OSError) as exc:
            send(client, AVAILABILITY_TOPIC, 'offline')
            print(f'Bitcoin Core unavailable: {exc}', file=sys.stderr)
            return 1
        send(client, STATE_TOPIC, json.dumps(state, separators=(',', ':')))
        send(client, AVAILABILITY_TOPIC, 'online')
        return 0
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'MQTT monitoring failed: {exc}', file=sys.stderr)
        sys.exit(1)

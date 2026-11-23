#!/usr/bin/env python3
"""Optional read-only Bitcoin Core -> Home Assistant MQTT Discovery bridge."""
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
}
BINARY_SENSORS = {
    'initial_download': ('Initial Block Download', 'initial_download'),
    'pruned': ('Pruning Enabled', 'pruned'),
    'synchronized': ('Synchronized', 'synchronized'),
}


def rpc(method):
    command = ['docker', 'exec', CONTAINER, 'bitcoin-cli',
               '-datadir=/home/bitcoin/.bitcoin', method]
    result = subprocess.run(command, capture_output=True, text=True,
                            check=True, timeout=20)
    return json.loads(result.stdout)


def snapshot():
    chain = rpc('getblockchaininfo')
    net = rpc('getnetworkinfo')
    blocks, headers = int(chain['blocks']), int(chain['headers'])
    ibd = bool(chain['initialblockdownload'])
    return {
        'blocks': blocks,
        'headers': headers,
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
        # Initial download complete + up to tip; do not equate progress alone to synced.
        'synchronized': not ibd and (headers - blocks) <= 1 and blocks > 0,
    }


def configs():
    discovery_prefix = os.environ.get('MQTT_DISCOVERY_PREFIX', 'homeassistant').strip('/')
    device = {'identifiers': [DEVICE_ID], 'name': 'Bitcoin Pi Node',
              'manufacturer': 'Community', 'model': 'Bitcoin Core (Docker)'}
    for key, (name, field, unit, state_class) in SENSORS.items():
        config = {'name': name, 'unique_id': f'{DEVICE_ID}_{key}',
                  'state_topic': STATE_TOPIC,
                  'value_template': '{{ value_json.' + field + ' }}',
                  'availability_topic': AVAILABILITY_TOPIC,
                  'device': device}
        if unit:
            config['unit_of_measurement'] = unit
        if state_class:
            config['state_class'] = state_class
        yield f'{discovery_prefix}/sensor/{DEVICE_ID}/{key}/config', config
    for key, (name, field) in BINARY_SENSORS.items():
        config = {'name': name, 'unique_id': f'{DEVICE_ID}_{key}',
                  'state_topic': STATE_TOPIC,
                  'value_template': "{{ 'ON' if value_json." + field + " else 'OFF' }}",
                  'payload_on': 'ON', 'payload_off': 'OFF',
                  'availability_topic': AVAILABILITY_TOPIC,
                  'device': device}
        yield f'{discovery_prefix}/binary_sensor/{DEVICE_ID}/{key}/config', config


def load_password():
    password_file = os.environ.get('MQTT_PASSWORD_FILE', '').strip()
    if password_file:
        path = Path(password_file)
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
        except (subprocess.SubprocessError, ValueError, KeyError) as exc:
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

import importlib.util
import pathlib
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'scripts' / 'bitcoin-ha-mqtt.py'
spec = importlib.util.spec_from_file_location('bitcoin_ha_mqtt', SCRIPT)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def fixture(ibd=True, blocks=100, peers=8):
    chain = {'blocks': blocks, 'headers': 110 if ibd else blocks,
             'initialblockdownload': ibd, 'verificationprogress': .9,
             'chain': 'main', 'pruned': True, 'pruneheight': 50,
             'size_on_disk': 1024 ** 3}
    net = {'connections': peers, 'connections_in': 3, 'connections_out': 5,
           'subversion': '/Satoshi:31.1.0/'}
    totals = {'totalbytesrecv': 2 * 1024 ** 3, 'totalbytessent': 1024 ** 3}
    return chain, net, totals


class BridgeTests(unittest.TestCase):
    def test_discovery_stable_and_expiry(self):
        configs = list(bridge.configs())
        self.assertEqual(len(configs), 21)
        self.assertEqual(len({v['unique_id'] for _, v in configs}), 21)
        self.assertTrue(all(v['expire_after'] == 300 for _, v in configs))
        self.assertTrue(all(v['state_topic'] == bridge.STATE_TOPIC for _, v in configs))
        self.assertIn('bitcoin_pi_node_blocks', [v['unique_id'] for _, v in configs])

    def test_synchronized_and_counter(self):
        chain, net, totals = fixture(False)
        state, cache = bridge.build_snapshot(chain, net, totals, 3600, 20.0, {}, 1000)
        self.assertTrue(state['synchronized'])
        self.assertEqual(state['uptime_seconds'], 3600)
        self.assertEqual(state['bytes_received_gib'], 2)
        self.assertEqual(state['storage_free_gib'], 20)
        self.assertEqual(state['sync_stalled_minutes'], 0)
        self.assertEqual(cache['blocks'], 100)

    def test_stall_only_during_ibd(self):
        chain, net, totals = fixture()
        old = {'blocks': 100, 'last_advance': 1000}
        state, cache = bridge.build_snapshot(chain, net, totals, 120, 10, old, 2860)
        self.assertTrue(state['sync_stalled'])
        self.assertEqual(state['sync_stalled_minutes'], 31)
        state, cache = bridge.build_snapshot(chain, net, totals, 120, 10, old, 1100)
        self.assertFalse(state['sync_stalled'])
        chain['initialblockdownload'] = False
        state, _ = bridge.build_snapshot(chain, net, totals, 120, 10, old, 2860)
        self.assertFalse(state['sync_stalled'])
        chain['initialblockdownload'] = True
        chain['blocks'] = 101
        state, cache = bridge.build_snapshot(chain, net, totals, 120, 10, old, 2860)
        self.assertFalse(state['sync_stalled'])
        self.assertEqual(cache['last_advance'], 2860)

    def test_storage_missing_does_not_falsely_report_ok(self):
        chain, net, totals = fixture()
        state, _ = bridge.build_snapshot(chain, net, totals, 100, None, {}, 200)
        self.assertIsNone(state['low_storage'])
        self.assertIsNone(state['storage_free_gib'])
        configs = dict(bridge.configs())
        self.assertIn('unknown', configs['homeassistant/binary_sensor/bitcoin_pi_node/low_storage/config']['value_template'])

    def test_peer_warning_and_low_storage(self):
        chain, net, totals = fixture(peers=0)
        state, _ = bridge.build_snapshot(chain, net, totals, 100, 4.5, {}, 200)
        self.assertTrue(state['no_peers'])
        self.assertTrue(state['low_storage'])

    def test_cache_roundtrip_and_permissions(self):
        with tempfile.TemporaryDirectory() as root:
            path = pathlib.Path(root) / 'cache' / 'status.json'
            bridge.write_cache(path, {'blocks': 123, 'last_advance': 42})
            self.assertEqual(bridge.read_cache(path)['blocks'], 123)
            self.assertEqual(path.stat().st_mode & 0o077, 0)

    def test_timers_and_limits_validate(self):
        with patch.dict('os.environ', {'BITCOIN_HA_EXPIRE_AFTER': '0'}):
            with self.assertRaises(ValueError):
                list(bridge.configs())


if __name__ == '__main__':
    unittest.main()

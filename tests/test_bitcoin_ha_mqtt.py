import importlib.util
import pathlib
import unittest
from unittest.mock import patch

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'scripts' / 'bitcoin-ha-mqtt.py'
spec = importlib.util.spec_from_file_location('bitcoin_ha_mqtt', SCRIPT)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class BridgeTests(unittest.TestCase):
    def test_discovery_unique_entities_and_topics(self):
        configs = list(bridge.configs())
        self.assertEqual(len(configs), 13)
        self.assertEqual(len({data['unique_id'] for _, data in configs}), 13)
        for topic, data in configs:
            self.assertTrue(topic.endswith('/config'))
            self.assertEqual(data['availability_topic'], bridge.AVAILABILITY_TOPIC)
            self.assertEqual(data['state_topic'], bridge.STATE_TOPIC)

    @patch.object(bridge, 'rpc')
    def test_snapshot_synchronized(self, rpc):
        rpc.side_effect = [
            {'blocks': 100, 'headers': 100, 'initialblockdownload': False,
             'verificationprogress': 0.99999, 'size_on_disk': 1073741824,
             'chain': 'main', 'pruned': True, 'pruneheight': 50},
            {'connections': 8, 'connections_in': 3, 'connections_out': 5,
             'subversion': '/Satoshi:31.1.0/'}]
        result = bridge.snapshot()
        self.assertTrue(result['synchronized'])
        self.assertEqual(result['disk_gib'], 1)
        self.assertEqual(result['peers'], 8)

    @patch.object(bridge, 'rpc')
    def test_initial_download_not_synced(self, rpc):
        rpc.side_effect = [
            {'blocks': 100, 'headers': 100, 'initialblockdownload': True,
             'verificationprogress': 1.0, 'chain': 'main'},
            {}]
        self.assertFalse(bridge.snapshot()['synchronized'])


if __name__ == '__main__':
    unittest.main()

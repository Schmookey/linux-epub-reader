"""MPRIS service fallback and local-cover security tests (no D-Bus bus needed)."""
import os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from mpris_service import MPRISBridge

class MPRISTests(unittest.TestCase):
    def test_local_cover_bytes_only_and_no_remote_lookups(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge = MPRISBridge(folder)
            self.assertEqual(bridge.store_art(None, 'a'), '')
            self.assertEqual(bridge.store_art(b'http://example.com/img', 'a'), '')
            jpeg = b'\xff\xd8\xff' + b'picture'
            uri = bridge.store_art(jpeg, '/fake/music/file.mp3')
            self.assertTrue(uri.startswith('file://'))
            self.assertIn('mpris-art', uri)
            self.assertTrue(list((Path(folder)/'mpris-art').iterdir()))
            self.assertEqual(bridge.store_art(jpeg, '/fake/music/file.mp3'), uri)

    def test_distinct_preview_and_stable_bus_names(self):
        a = MPRISBridge('/tmp', preview=False)
        b = MPRISBridge('/tmp', preview=True)
        self.assertNotEqual(a._name, b._name)
        self.assertTrue(a._name.startswith('org.mpris.MediaPlayer2.'))
        self.assertEqual(b.snapshot()['status'], 'Stopped')

if __name__ == '__main__':
    unittest.main()

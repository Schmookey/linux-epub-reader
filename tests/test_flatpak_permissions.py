"""Keep external-drive Flatpak access read-only and narrowly scoped.

The native Tk file chooser cannot use a Flatpak portal, so mounted drives
must be explicitly exposed. Test both packaging variants and their state paths.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FlatpakExternalMediaPermissionsTests(unittest.TestCase):
    def test_mounts_are_visible_but_read_only_in_both_manifests(self):
        for name, state_dir in (
            ("io.github.schmookey.LinuxEpubReader.yml",
             "linux-epub-reader"),
            ("io.github.schmookey.LinuxEpubReader.Preview.yml",
             "linux-epub-reader-preview"),
        ):
            with self.subTest(manifest=name):
                lines = (ROOT / name).read_text(encoding='utf-8').splitlines()
                start = lines.index('finish-args:') + 1
                end = lines.index('modules:')
                permissions = [x.strip().removeprefix('- ').strip()
                               for x in lines[start:end] if x.lstrip().startswith('- ')]
                for root in ('/media', '/run/media', '/mnt'):
                    self.assertIn(f'--filesystem={root}:ro', permissions)
                    self.assertNotIn(f'--filesystem={root}', permissions)
                self.assertIn('--filesystem=home:ro', permissions)
                self.assertIn(f'--filesystem=~/.local/share/{state_dir}:create', permissions)
                self.assertNotIn('--filesystem=host', permissions)
                self.assertNotIn('--filesystem=host:ro', permissions)
                self.assertNotIn('--share=network', permissions)


if __name__ == '__main__':
    unittest.main()

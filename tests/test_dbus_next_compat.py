"""Regression checks for bundled dbus-next Python 3.15 compatibility patch."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'packaging/flatpak/patch_dbus_next.py'
spec = importlib.util.spec_from_file_location('patch_dbus_next', SCRIPT)
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)


class DbusNextPython315PatchTests(unittest.TestCase):
    def test_patch_is_idempotent_and_compiles(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'service.py'
            target.write_text(
                'from functools import wraps\n'
                'from typing import no_type_check_decorator, Dict, List, Any\n'
                '@no_type_check_decorator\n'
                'def a_decorator(fn):\n'
                '    return fn\n',
                encoding='utf-8'
            )
            self.assertTrue(compat.patch_dbus_next_service(target))
            self.assertFalse(compat.patch_dbus_next_service(target))
            patched = target.read_text(encoding='utf-8')
            self.assertNotIn('from typing import no_type_check_decorator', patched)
            namespace = {}
            exec(compile(patched, str(target), 'exec'), namespace)
            @namespace['a_decorator']
            def f(value: 's'):
                return value
            self.assertEqual(f('works'), 'works')
            self.assertTrue(getattr(f, '__no_type_check__', False))

    def test_unexpected_upstream_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'service.py'
            target.write_text('from typing import Callable\n', encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'Unexpected dbus-next'):
                compat.patch_dbus_next_service(target)


if __name__ == '__main__':
    unittest.main()

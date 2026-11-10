from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from mivo_m82 import autostart

class Key:
    def __enter__(self): return self
    def __exit__(self, *_): pass

class AutostartTests(unittest.TestCase):
    def test_install_copies_package_and_uninstall_keeps_other_entries(self):
        values = {'OtherApplication': 'keep'}
        def delete(key, name):
            if name not in values: raise FileNotFoundError(name)
            del values[name]
        registry = SimpleNamespace(HKEY_CURRENT_USER=1, REG_SZ=1,
            CreateKey=lambda *_: Key(), SetValueEx=lambda _, n, __, ___, v: values.update({n:v}),
            DeleteValue=delete)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            python = root/'Python with spaces/python.exe'
            python.parent.mkdir(); python.touch(); python.with_name('pythonw.exe').touch()
            install = root/'Installed Clock'
            with patch.dict('sys.modules', {'winreg': registry}), \
                 patch.object(autostart, 'install_dir', return_value=install), \
                 patch.object(autostart.sys, 'executable', str(python)):
                result = autostart.install()
                self.assertEqual(result['run_value'], 'MIVO_M82_Clock')
                self.assertTrue((install/'mivo_m82/protocol.py').is_file())
                compile((install/'launch_clock.py').read_text(), '<launcher>', 'exec')
                compile((install/'sync_once.py').read_text(), '<sync>', 'exec')
                self.assertIn('pythonw.exe', values['MIVO_M82_Clock'])
                autostart.uninstall()
                self.assertEqual(values, {'OtherApplication': 'keep'})
                self.assertTrue((install/'mivo_m82/protocol.py').is_file())

if __name__ == '__main__':
    unittest.main()

"""Window sizing on common high-DPI laptop work areas."""
import unittest
from pathlib import Path
import subprocess
import sys
import tempfile
from runtime_support import fit_window, downloads_folder


class RuntimeTests(unittest.TestCase):
    def test_fits_standard_and_high_dpi_screens(self):
        for width, height in ((1920,1040),(1366,728),(1366/1.5,728/1.5),(1920/2,1040/2)):
            size, minimum = fit_window(width,height)
            self.assertLessEqual(size[0],width)
            self.assertLessEqual(size[1],height)
            self.assertLessEqual(minimum[0],size[0])
            self.assertLessEqual(minimum[1],size[1])

    def test_save_dialog_default_is_an_existing_user_directory(self):
        self.assertTrue(Path(downloads_folder()).is_dir())

    def test_missing_webview_exits_without_deadlocking_server_shutdown(self):
        with tempfile.TemporaryDirectory() as data:
            code = '''
import builtins, sys
import app
old_import = builtins.__import__
def intercept(name, *args, **kwargs):
    if name == 'webview': raise ImportError('simulated missing dependency')
    return old_import(name, *args, **kwargs)
builtins.__import__ = intercept
sys.argv = ['app.py', '--port', '0', '--data', sys.argv[1]]
try:
    app.main()
except RuntimeError:
    sys.exit(0)
sys.exit(1)
'''
            result = subprocess.run([sys.executable,'-c',code,data],cwd=Path(__file__).parent,
                                    capture_output=True,timeout=8)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)

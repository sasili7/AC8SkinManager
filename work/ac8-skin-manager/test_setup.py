"""Exercise the distributed setup against isolated game roots, never the live game."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parent
ROOT = PROJECT.parents[1]
RELEASE = Path(os.getenv('AC8_TEST_RELEASE', str(ROOT / 'outputs/ac8-skin-manager/AC8SkinManager-0.8.0-ModOnly')))
REAL = Path('C:/Program Files (x86)/Steam/steamapps/common/ACE COMBAT 8')
REL = Path('Game/Binaries/Win64')


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ac8-setup-')
        self.addCleanup(self.temp.cleanup)
        self.game = Path(self.temp.name) / 'Steam Library/Game With Spaces'
        self.win = self.game / REL
        self.win.mkdir(parents=True)
        os.link(REAL / REL / 'AceCombat8.exe', self.win / 'AceCombat8.exe')
        (self.game / 'EasyAntiCheat').mkdir()
        self.eac = {'productid': 'fixture-product', 'sandboxid': 'fixture-sandbox',
                    'deploymentid': 'fixture-deployment', 'executable': 'Original.exe', 'hide_gui': 'false'}
        (self.game / 'EasyAntiCheat/Settings.json').write_text(json.dumps(self.eac))

    def run_setup(self, *flags, expected=0, release=RELEASE):
        result = subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',
                                 str(release / 'Setup.ps1'),'-GamePath',str(self.game),'-NoUI',*flags],
                                capture_output=True,text=True,errors='replace',timeout=70,creationflags=0x08000000)
        self.assertEqual(result.returncode,expected,result.stdout+result.stderr)
        # PowerShell wraps error text mid-word based on the path/title width.
        result.stderr = result.stderr.replace('\r', '').replace('\n', '')
        return result

    def test_clean_install_and_rerun_preserve_existing_settings(self):
        self.run_setup('-InstallUE4SS','-ConfigureOffline')
        self.assertTrue((self.win / 'ue4ss/Mods/AC8SkinManager/Scripts/main.lua').is_file())
        self.assertTrue((self.win / 'dwmapi.dll').is_file())
        self.assertEqual((self.win / 'steam_appid.txt').read_text(),'2288340')
        self.assertEqual(json.loads((self.game / 'EasyAntiCheat/Settings.json').read_text()),self.eac)
        offline = json.loads((self.game / 'EasyAntiCheat/AC8SkinManager_Offline.json').read_text())
        self.assertEqual(offline['allow_null_client'],'true')
        self.assertEqual(offline['productid'],self.eac['productid'])
        settings = self.win / 'ue4ss/UE4SS-settings.ini'
        settings.write_text(settings.read_text()+'\n; preserved-user-value\n')
        before = settings.read_bytes()
        self.run_setup('-InstallUE4SS','-ConfigureOffline')
        self.assertEqual(settings.read_bytes(),before)

    def test_no_ue4ss_selection_does_not_install_it(self):
        result = self.run_setup(expected=1)
        self.assertIn('Install UE4SS first',result.stderr)
        self.assertFalse((self.win / 'dwmapi.dll').exists())
        self.assertFalse((self.win / 'ue4ss/UE4SS.dll').exists())

    def test_foreign_proxy_is_preserved_before_any_prerequisite_writes(self):
        proxy = self.win / 'dwmapi.dll'; proxy.write_bytes(b'another mod')
        result = self.run_setup('-InstallUE4SS',expected=1)
        self.assertIn('another loader',result.stderr)
        self.assertEqual(proxy.read_bytes(),b'another mod')
        self.assertFalse((self.win / 'ue4ss/UE4SS.dll').exists())

    def test_failure_rolls_back_new_prerequisites_and_offline_files(self):
        legacy = self.win / 'ue4ss/Mods/IoStoreLoaderMod'
        legacy.mkdir(parents=True); (legacy / 'enabled.txt').touch()
        result = self.run_setup('-InstallUE4SS','-ConfigureOffline',expected=1)
        self.assertIn('Disable the legacy',result.stderr)
        self.assertTrue((legacy / 'enabled.txt').is_file())
        for path in ('dwmapi.dll','ue4ss/UE4SS.dll','steam_appid.txt'):
            self.assertFalse((self.win / path).exists(),path)
        self.assertFalse((self.game / 'EasyAntiCheat/AC8SkinManager_Offline.json').exists())
        self.assertEqual(json.loads((self.game / 'EasyAntiCheat/Settings.json').read_text()),self.eac)

    def test_package_tamper_is_refused_before_copying(self):
        copy = Path(self.temp.name) / 'release'
        shutil.copytree(RELEASE,copy)
        (copy / 'Prerequisites/UE4SS/Game/Binaries/Win64/dwmapi.dll').write_bytes(b'tampered')
        result = self.run_setup('-InstallUE4SS',expected=1,release=copy)
        self.assertIn('Package checksum mismatch',result.stderr)
        self.assertFalse((self.win / 'dwmapi.dll').exists())

    def test_partial_runtime_without_bootstrap_requires_repair_selection(self):
        (self.win / 'ue4ss').mkdir()
        bundled = RELEASE / 'Prerequisites/UE4SS/Game/Binaries/Win64'
        shutil.copy2(bundled / 'ue4ss/UE4SS.dll', self.win / 'ue4ss/UE4SS.dll')
        result = self.run_setup(expected=1)
        self.assertIn('Incomplete UE4SS', result.stderr)
        self.assertFalse((self.win / 'ue4ss/Mods/AC8SkinManager').exists())
        self.run_setup('-InstallUE4SS')
        self.assertTrue((self.win / 'dwmapi.dll').is_file())
        self.assertTrue((self.win / 'ue4ss/UE4SS-settings.ini').is_file())

    def test_foreign_proxy_is_refused_when_ue4ss_option_is_unchecked(self):
        bundled = RELEASE / 'Prerequisites/UE4SS/Game/Binaries/Win64'
        shutil.copytree(bundled, self.win, dirs_exist_ok=True)
        proxy = self.win / 'dwmapi.dll'; proxy.write_bytes(b'foreign proxy')
        result = self.run_setup(expected=1)
        self.assertIn('another loader', result.stderr)
        self.assertEqual(proxy.read_bytes(), b'foreign proxy')
        self.assertFalse((self.win / 'ue4ss/Mods/AC8SkinManager').exists())

    def test_incomplete_original_offline_settings_stop_before_writes(self):
        (self.game / 'EasyAntiCheat/Settings.json').write_text('{"productid":"only-one-field"}')
        result = self.run_setup('-InstallUE4SS', '-ConfigureOffline', expected=1)
        self.assertIn('Incomplete original EAC settings', result.stderr)
        self.assertFalse((self.win / 'dwmapi.dll').exists())

    def test_conflicting_appid_is_preserved_before_installation(self):
        path = self.win / 'steam_appid.txt'; path.write_text('999999')
        result = self.run_setup('-InstallUE4SS', '-ConfigureOffline', expected=1)
        self.assertIn('steam_appid.txt differs', result.stderr)
        self.assertEqual(path.read_text(), '999999')
        self.assertFalse((self.win / 'dwmapi.dll').exists())

    def test_ascii_game_folder_with_shell_and_wildcard_characters(self):
        renamed = self.game.with_name('AC8 & (Retail) [1]')
        self.game.rename(renamed)
        self.game = renamed; self.win = renamed / REL
        self.run_setup('-InstallUE4SS', '-ConfigureOffline')
        self.assertTrue((self.win / 'ue4ss/Mods/AC8SkinManager/Scripts/main.lua').is_file())

    def test_release_extracted_under_unicode_folder_works(self):
        copy = Path(self.temp.name) / '下载目录 测试/安装包'
        shutil.copytree(RELEASE,copy)
        self.run_setup('-InstallUE4SS','-ConfigureOffline',release=copy)
        self.assertTrue((self.win / 'ue4ss/Mods/AC8SkinManager/Scripts/main.lua').is_file())

    def test_mod_only_release_has_no_apps_skins_or_vc_installer(self):
        if (RELEASE / 'AC8SkinPackTool.exe').is_file():
            self.skipTest('This distribution intentionally includes the desktop tool.')
        files = [p.relative_to(RELEASE).as_posix() for p in RELEASE.rglob('*') if p.is_file()]
        self.assertFalse(any(name.lower().endswith(('.exe','.pak','.utoc','.ucas')) for name in files))
        self.assertFalse(any('vcredist' in name.lower() for name in files))
        setup = (RELEASE / 'Setup.ps1').read_text(encoding='utf-8-sig')
        self.assertNotIn('Invoke-WebRequest',setup)
        self.assertNotIn('InstallVCRuntime',setup)
        self.assertTrue((RELEASE / 'Licenses/UE4SS-MIT.txt').is_file())


if __name__ == '__main__':
    unittest.main(verbosity=2)

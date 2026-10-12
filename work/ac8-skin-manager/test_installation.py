"""First-install/update/refusal tests in isolated game directories."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parent
ROOT = PROJECT.parents[1]
RELEASE = Path(os.getenv('AC8_TEST_RELEASE', str(ROOT / 'outputs/ac8-skin-manager/AC8SkinManager-0.8.0-ModOnly')))
sys.path.insert(0, str(PROJECT / 'package-tool'))
from compatibility import preflight, CompatibilityError, digest

REAL_GAME = Path('C:/Program Files (x86)/Steam/steamapps/common/ACE COMBAT 8')
REL = Path('Game/Binaries/Win64/ue4ss/Mods')


class InstallationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='ac8-install-')
        cls.base = Path(cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def game(self, installed=False):
        game = Path(tempfile.mkdtemp(prefix='player-', dir=self.base))
        binary = game / 'Game/Binaries/Win64'
        (binary / 'ue4ss/Mods').mkdir(parents=True)
        # Read-only hard link. Tests replacing the EXE must unlink first.
        os.link(REAL_GAME / 'Game/Binaries/Win64/AceCombat8.exe', binary / 'AceCombat8.exe')
        shutil.copy2(REAL_GAME / 'Game/Binaries/Win64/ue4ss/UE4SS.dll', binary / 'ue4ss/UE4SS.dll')
        bundled = RELEASE / 'Prerequisites/UE4SS/Game/Binaries/Win64'
        for relative in ('dwmapi.dll', 'ue4ss/UE4SS-settings.ini'):
            shutil.copy2(bundled / relative, binary / relative)
        if installed:
            shutil.copytree(RELEASE / REL, game / REL, dirs_exist_ok=True)
        return game

    def install(self, game, expected=0):
        result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                 str(RELEASE / 'Install-Manager.ps1'), '-GamePath', str(game)],
                                capture_output=True, text=True, errors='replace', creationflags=0x08000000)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        # PowerShell wraps error text based on the full script-path width.
        result.stderr = result.stderr.replace('\r', '').replace('\n', '')
        if expected == 0:
            for source in (RELEASE / REL / 'AC8SkinManager/Scripts').glob('*.lua'):
                self.assertEqual((game / REL / 'AC8SkinManager/Scripts' / source.name).read_bytes(),
                                 source.read_bytes(), source.name)
        return result

    def test_first_install_enables_both_without_clearing_other_mods(self):
        game = self.game(); mods = game / REL
        (mods / 'mods.txt').write_text('AnotherMod : 1\nAC8OverrideLoader : 0\n', encoding='utf-8')
        (mods / 'mods.json').write_text('[{"mod_name":"OtherJson","mod_enabled":true},{"mod_name":"AC8OverrideLoader","mod_enabled":false}]', encoding='utf-8')
        self.install(game)
        expected = json.loads((RELEASE / REL / 'AC8SkinManager/compatibility.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(preflight(game)['release'], expected['release'])
        if expected.get('binding_capture_schema') == 1:
            self.assertTrue((mods / 'AC8SkinManager/Scripts/binding_capture.lua').is_file())
            self.assertTrue((mods / 'AC8SkinManager/BindingProfiles').is_dir())
        self.assertIn('AnotherMod : 1', (mods / 'mods.txt').read_text())
        rows = json.loads((mods / 'mods.json').read_text())
        self.assertIn({'mod_name': 'OtherJson', 'mod_enabled': True}, rows)
        self.assertTrue((mods / 'AC8SkinManager/enabled.txt').is_file())
        self.assertTrue((mods / 'AC8OverrideLoader/enabled.txt').is_file())

    def test_update_preserves_selections_configuration_and_other_skins(self):
        game = self.game(installed=True); mods = game / REL
        custom = {
            'AC8SkinManager/config.json': '{"runtime_switch_enabled":false}',
            'AC8SkinManager/selections.json': '{"selections":{"PP0021_su57":"custom"}}',
            'AC8SkinManager/Skins/other/PP0021_su57/blue/skin.json': '{"custom":true}',
            'AC8OverrideLoader/payloads/other/other.utoc': 'other-author-payload'}
        for name, text in custom.items():
            path = mods / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text, encoding='utf-8')
        before = {name: digest(mods / name) for name in custom}
        self.install(game)
        self.assertEqual(before, {name: digest(mods / name) for name in custom})
        self.assertTrue(list((game / 'Game/Binaries/Win64/AC8SkinManager-Backups').glob('*/AC8SkinManager/selections.json')))

    def test_core_install_refuses_incomplete_bootstrap_before_writes(self):
        game = self.game()
        (game / 'Game/Binaries/Win64/dwmapi.dll').unlink()
        result = self.install(game, expected=1)
        self.assertIn('Incomplete UE4SS', result.stderr)
        self.assertFalse((game / REL / 'AC8SkinManager').exists())

    def test_locked_destination_rolls_back_previously_copied_files(self):
        import ctypes
        from ctypes import wintypes
        game = self.game(installed=True); manager = game / REL / 'AC8SkinManager'
        catalog = manager / 'catalog.json'
        catalog.write_bytes(b'{"existing_catalog":true}')
        before = {p.relative_to(manager).as_posix(): p.read_bytes() for p in manager.rglob('*') if p.is_file()}
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateFileW(str(manager / 'Native/registrar.dll'), 0x80000000, 1, None, 3, 0, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            self.install(game, expected=1)
            after = {p.relative_to(manager).as_posix(): p.read_bytes() for p in manager.rglob('*') if p.is_file()}
            self.assertEqual(before, after)
        finally:
            kernel.CloseHandle(handle)

    def test_unsupported_executable_does_not_create_mod_files(self):
        game = self.game(); exe = game / 'Game/Binaries/Win64/AceCombat8.exe'
        exe.unlink(); exe.write_bytes(b'unsupported build')
        result = self.install(game, expected=1)
        self.assertIn('Unsupported AC8', result.stderr)
        self.assertEqual(list((game / REL).iterdir()), [])

    def test_legacy_loader_is_not_removed_automatically(self):
        game = self.game(); legacy = game / REL / 'IoStoreLoaderMod'
        legacy.mkdir(); (legacy / 'enabled.txt').touch()
        result = self.install(game, expected=1)
        self.assertIn('Disable the legacy', result.stderr)
        self.assertTrue((legacy / 'enabled.txt').is_file())
        self.assertFalse((game / REL / 'AC8SkinManager').exists())

    def test_disabled_legacy_marker_does_not_block_install(self):
        game = self.game(); mods = game / REL
        (mods / 'IoStoreLoaderMod').mkdir(); (mods / 'IoStoreLoaderMod/enabled.txt').touch()
        (mods / 'mods.txt').write_text('IoStoreLoaderMod : 0\n')
        self.install(game)
        preflight(game)

    def test_non_ascii_game_path_refused_before_writes(self):
        game = self.game(); moved = game.with_name(game.name + '-游戏')
        game.rename(moved)
        self.assertIn('ASCII', self.install(moved, expected=1).stderr)
        self.assertEqual(list((moved / REL).iterdir()), [])
        with self.assertRaisesRegex(CompatibilityError, 'ASCII'):
            preflight(moved)

    def test_app_local_wrong_architecture_runtime_refused(self):
        game = self.game()
        (game / 'Game/Binaries/Win64/MSVCP140.dll').write_bytes(b'wrong runtime')
        self.assertIn('x64', self.install(game, expected=1).stderr)
        self.assertEqual(list((game / REL).iterdir()), [])

    def test_redirected_existing_mod_directory_refused_before_backup(self):
        game = self.game(); mods = game / REL
        external = self.base / ('external-' + game.name); external.mkdir()
        (external / 'keep.txt').write_text('another-location')
        linked = mods / 'AC8SkinManager'
        # The junction and target are both inside the isolated test directory.
        script = game / 'make-test-junction.ps1'
        script.write_text('param([string]$Junction,[string]$Target)\nNew-Item -ItemType Junction -Path $Junction -Target $Target | Out-Null\n')
        subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),str(linked),str(external)],
                       check=True,capture_output=True,creationflags=0x08000000)
        try:
            result = self.install(game,expected=1)
            self.assertIn('Redirected install',result.stderr)
            self.assertEqual((external / 'keep.txt').read_text(),'another-location')
            self.assertFalse((game / 'Game/Binaries/Win64/AC8SkinManager-Backups').exists())
        finally:
            os.rmdir(linked)

    def test_import_refuses_changed_registrar_or_runtime(self):
        game = self.game(installed=True)
        preflight(game)
        binary = game / REL / 'AC8SkinManager/Native/registrar.dll'
        binary.write_bytes(b'changed')
        with self.assertRaisesRegex(CompatibilityError, 'checksum'):
            preflight(game)
        shutil.copy2(RELEASE / REL / 'AC8SkinManager/Native/registrar.dll', binary)
        runtime = game / 'Game/Binaries/Win64/ue4ss/UE4SS.dll'
        runtime.write_bytes(b'wrong architecture or missing runtime')
        with self.assertRaises(CompatibilityError):
            preflight(game)

    def test_explicitly_disabled_loader_blocks_import(self):
        game = self.game(installed=True)
        (game / REL / 'mods.json').write_text('[{"mod_name":"AC8OverrideLoader","mod_enabled":false}]', encoding='utf-8')
        with self.assertRaisesRegex(CompatibilityError, 'not enabled'):
            preflight(game)


if __name__ == '__main__':
    unittest.main(verbosity=2)

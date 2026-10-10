"""Integration checks use a real converted texture package and isolated game roots."""
from pathlib import Path
import json
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from packaging_core import Tool, PackageError, MOD_REL, LOADER_REL, REGISTRAR_REVISION, save_json, digest, extract_zip

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / 'work/ac8-skin-manager/package-tool-data/author-vrowe3xo/sasili__PP0021_su57__kamome_package_demo.ac8skin.zip'
RETOC = ROOT / 'work/ac8-kamome/tools/retoc/retoc.exe'


@unittest.skipUnless(FIXTURE.is_file(), "Optional user-supplied livery fixture is absent")
class PackageIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='ac8-pack-check-')
        cls.root = Path(cls.temp.name)
        cls.tool = Tool(RETOC, cls.root / 'jobs')
        cls.inspected = cls.tool.inspect_player(FIXTURE)
        # These tests exercise conversion and transaction semantics. Binary
        # compatibility is covered separately with actual PE headers and hashes.
        cls.compatibility_patch = patch('packaging_core.preflight', return_value={})
        cls.compatibility_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.compatibility_patch.stop()
        cls.temp.cleanup()

    def game(self):
        root = Path(tempfile.mkdtemp(dir=self.root))
        for name in ('Game/Binaries/Win64/AceCombat8.exe', MOD_REL / 'Scripts/main.lua',
                     MOD_REL / 'Native/registrar.dll', LOADER_REL / 'dlls/main.dll'):
            file = root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b'test fixture')
        (root / MOD_REL / 'Scripts/adapter.lua').write_text('-- ' + REGISTRAR_REVISION)
        save_json(root / MOD_REL / 'config.json', {'runtime_switch_enabled': True, 'package_registration_enabled': True})
        return root

    def snapshot(self, game):
        return {str(p.relative_to(game)): digest(p) for p in game.rglob('*') if p.is_file()
                and 'PackageBackups' not in p.parts and not any(part.startswith('pack-install-') for part in p.parts)}

    def test_author_import_of_three_converted_resource_files_suggests_su57_slots(self):
        with tempfile.TemporaryDirectory(dir=self.root) as scratch:
            extracted = extract_zip(FIXTURE, Path(scratch) / 'package')
            info = self.tool.inspect(extracted / 'resources')
            self.assertEqual(info['aircraft_id'], 'PP0021_su57')
            self.assertEqual(len(info['assets']), 1)
            self.assertEqual(info['assets'][0]['slots'], [10, 13])
            self.assertEqual(info['assets'][0]['parameter'], 'BaseColor')
            self.assertEqual(info['source_identity'], {'provider_id': 'sasili', 'id': 'kamome_package_demo'})

    def test_install_update_and_keep_shared_files(self):
        game = self.game(); before = self.snapshot(game)
        result = self.tool.install(self.inspected, game, running=lambda: False)
        self.assertTrue(result['installed'])
        for file, sha in before.items():
            self.assertEqual(digest(game / file), sha)
        installed = self.snapshot(game)
        result = self.tool.install(self.inspected, game, running=lambda: False)
        self.assertEqual(self.snapshot(game), installed)
        self.assertTrue((Path(result['backup']) / '0/skin.json').is_file())
        self.assertTrue((Path(result['backup']) / '1').is_dir())
        self.assertTrue((Path(result['backup']) / '2').is_file())

    def test_failed_update_rolls_back_every_target(self):
        for fail_at in (0, 1, 2):
            with self.subTest(fail_at=fail_at):
                game = self.game()
                self.tool.install(self.inspected, game, running=lambda: False)
                before = self.snapshot(game)
                def fault(index):
                    if index == fail_at:
                        raise OSError('simulated disk failure')
                with self.assertRaises(OSError):
                    self.tool.install(self.inspected, game, running=lambda: False, fault=fault)
                self.assertEqual(self.snapshot(game), before)

    def test_running_game_and_incompatible_manager_do_not_write(self):
        game = self.game(); before = self.snapshot(game)
        with self.assertRaisesRegex(PackageError, '退出'):
            self.tool.install(self.inspected, game, running=lambda: True)
        self.assertEqual(self.snapshot(game), before)
        save_json(game / MOD_REL / 'config.json', {})
        before = self.snapshot(game)
        with self.assertRaisesRegex(PackageError, '不兼容'):
            self.tool.install(self.inspected, game, running=lambda: False)
        self.assertEqual(self.snapshot(game), before)

    def test_foreign_skin_and_resource_collision_do_not_overwrite(self):
        skin = self.inspected['manifest']; game = self.game()
        target = game / MOD_REL / 'Skins' / skin['provider_id'] / skin['aircraft_id'] / skin['id']
        target.mkdir(parents=True); (target / 'skin.json').write_text('foreign package')
        before = self.snapshot(game)
        with self.assertRaisesRegex(PackageError, '其它方式'):
            self.tool.install(self.inspected, game, running=lambda: False)
        self.assertEqual(self.snapshot(game), before)
        game = self.game()
        header = game / MOD_REL / 'Native/containers/other.bin'; header.parent.mkdir(parents=True)
        header.write_bytes((Path(self.inspected['source']) / 'registration/container.bin').read_bytes())
        before = self.snapshot(game)
        with self.assertRaisesRegex(PackageError, '冲突'):
            self.tool.install(self.inspected, game, running=lambda: False)
        self.assertEqual(self.snapshot(game), before)

    def archive(self, entries):
        path = self.root / ('bad-' + str(len(list(self.root.glob('bad-*')))) + '.zip')
        with zipfile.ZipFile(path, 'w') as out:
            for name, value in entries:
                out.writestr(name, value)
        return path

    def test_zip_traversal_and_case_collision_rejected_before_writes(self):
        for entries in ([('okay.txt', 'a'), ('../outside.txt', 'b')],
                        [('A/file.txt', 'a'), ('a/FILE.txt', 'b')],
                        [('CON.txt', 'a')], [('C:/bad.txt', 'a')]):
            folder = Path(tempfile.mkdtemp(dir=self.root))
            with self.assertRaises(PackageError):
                extract_zip(self.archive(entries), folder)
            self.assertEqual(list(folder.iterdir()), [])

    def test_tamper_and_unregistered_script_rejected(self):
        with zipfile.ZipFile(FIXTURE) as source:
            original = [(name, source.read(name)) for name in source.namelist()]
        for entries in ([(name, b'changed' if name == 'skin.json' else value) for name, value in original],
                        original + [('install.cmd', b'echo no')]):
            with self.assertRaises(PackageError):
                self.tool.inspect_player(self.archive(entries))

    def test_preinstall_recheck_detects_changed_extracted_file(self):
        inspected = self.tool.inspect_player(FIXTURE)
        (Path(inspected['source']) / 'skin.json').write_text('{}')
        game = self.game(); before = self.snapshot(game)
        with self.assertRaisesRegex(PackageError, '校验失败'):
            self.tool.install(inspected, game, running=lambda: False)
        self.assertEqual(self.snapshot(game), before)

    def test_missing_companion_and_multiple_containers(self):
        folder = Path(tempfile.mkdtemp(dir=self.root))
        (folder / 'a.utoc').write_bytes(b'incomplete')
        with self.assertRaisesRegex(PackageError, 'UCAS'):
            self.tool.inspect(folder)
        (folder / 'b.utoc').write_bytes(b'incomplete')
        with self.assertRaisesRegex(PackageError, '多个容器'):
            self.tool.inspect(folder)


if __name__ == '__main__':
    unittest.main(verbosity=2)

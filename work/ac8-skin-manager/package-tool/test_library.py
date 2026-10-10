"""Owned-file removal, recovery, selection and localization regression checks."""
from pathlib import Path
import ast
import hashlib
import json
import os
import re
import tempfile
import unittest
from unittest.mock import patch
from packaging_core import Tool, PackageError, MOD_REL, LOADER_REL, save_json
from library import Library, identity_parts
from i18n import english

ROOT = Path(__file__).resolve().parents[3]
PROJECT = Path(__file__).resolve().parent
FIXTURE = ROOT / 'work/ac8-skin-manager/package-tool-data/author-vrowe3xo/sasili__PP0021_su57__kamome_package_demo.ac8skin.zip'


@unittest.skipUnless(FIXTURE.is_file(), "Optional user-supplied livery fixture is absent")
class LibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='ac8-library-')
        cls.root = Path(cls.temp.name)
        cls.tool = Tool(ROOT / 'work/ac8-kamome/tools/retoc/retoc.exe', cls.root / 'jobs')
        cls.inspected = cls.tool.inspect_player(FIXTURE)
        cls.identity = cls.inspected['identity']
        cls.plane = cls.inspected['manifest']['aircraft_id']

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def fixture(self):
        game = Path(tempfile.mkdtemp(dir=self.root))
        for relative in ('Game/Binaries/Win64/AceCombat8.exe', MOD_REL / 'Scripts/main.lua',
                         MOD_REL / 'Native/registrar.dll', LOADER_REL / 'dlls/main.dll'):
            path = game / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'fixture')
        (game / MOD_REL / 'Scripts/adapter.lua').write_text('-- 20261008-cached-store')
        save_json(game / MOD_REL / 'config.json', {'runtime_switch_enabled': True, 'package_registration_enabled': True})
        with patch('packaging_core.preflight', return_value={}):
            self.tool.install(self.inspected, game, running=lambda: False)
        return game, Library(game)

    def snapshot(self, game, include_trash=False):
        return {str(p.relative_to(game)):hashlib.sha256(p.read_bytes()).hexdigest() for p in game.rglob('*') if p.is_file()
                and (include_trash or 'RemovedPackages' not in p.parts) and 'PackageBackups' not in p.parts}

    def test_remove_selected_skin_restores_std_but_preserves_other_aircraft(self):
        game, lib = self.fixture()
        selection = {'selections': {self.plane:self.identity, 'PP0022_f16c':'other__PP0022_f16c__blue'}, 'extra':'keep'}
        for name in ('selections.json','selections.json.bak'):save_json(game / MOD_REL / name, selection)
        original = self.snapshot(game)
        row = lib.installed()[0];self.assertTrue(row['managed'] and row['complete'] and row['selected'])
        result = lib.remove(self.identity, running=lambda:False)
        self.assertEqual(lib.installed(), [])
        self.assertEqual(len(lib.removed()), 1)
        for target in lib.targets(self.identity):self.assertFalse(target.exists())
        for name in ('selections.json','selections.json.bak'):
            value = json.loads((game / MOD_REL / name).read_text())
            self.assertEqual(value['selections'][self.plane], 'original')
            self.assertEqual(value['selections']['PP0022_f16c'], selection['selections']['PP0022_f16c'])
            self.assertEqual(value['extra'], 'keep')
        lib.restore(result['removal_id'], running=lambda:False)
        self.assertEqual(len(lib.installed()), 1);self.assertEqual(lib.removed(), [])
        self.assertFalse(lib.installed()[0]['selected'])
        for name, sha in original.items():
            if 'selections.json' not in name:self.assertEqual(self.snapshot(game)[name],sha,name)

    def test_remove_rolls_back_all_moved_files_and_selection_on_failure(self):
        for fail_at in range(4):
            with self.subTest(fail_at=fail_at):
                game,lib=self.fixture();save_json(game / MOD_REL / 'selections.json', {'selections':{self.plane:self.identity}})
                before=self.snapshot(game)
                def fault(index):
                    if index==fail_at:raise OSError('simulated write failure')
                with self.assertRaises(OSError):lib.remove(self.identity,running=lambda:False,fault=fault)
                self.assertEqual(self.snapshot(game),before);self.assertEqual(lib.removed(),[])

    def test_restore_rolls_back_partial_moves_and_can_be_retried(self):
        for fail_at in range(3):
            with self.subTest(fail_at=fail_at):
                game,lib=self.fixture();removed=lib.remove(self.identity,running=lambda:False)
                before=self.snapshot(game,True)
                def fault(index):
                    if index==fail_at:raise OSError('simulated move failure')
                with self.assertRaises(OSError):lib.restore(removed['removal_id'],running=lambda:False,fault=fault)
                self.assertEqual(self.snapshot(game,True),before)
                lib.restore(removed['removal_id'],running=lambda:False);self.assertTrue(lib.installed()[0]['complete'])

    def test_running_game_refuses_remove_and_restore(self):
        game,lib=self.fixture();before=self.snapshot(game)
        with self.assertRaisesRegex(PackageError,'退出'):lib.remove(self.identity,running=lambda:True)
        self.assertEqual(self.snapshot(game),before)
        removed=lib.remove(self.identity,running=lambda:False);before=self.snapshot(game,True)
        with self.assertRaisesRegex(PackageError,'退出'):lib.restore(removed['removal_id'],running=lambda:True)
        self.assertEqual(self.snapshot(game,True),before)

    def test_manual_installs_and_foreign_extra_files_are_read_only(self):
        for foreign in (False,True):
            game,lib=self.fixture();skin=lib.targets(self.identity)[0]
            if foreign:(skin/'other-author.txt').write_text('preserve')
            else:(skin/'installed-package.json').unlink()
            before=self.snapshot(game);self.assertFalse(lib.installed()[0]['managed'])
            with self.assertRaises((PackageError,OSError)):lib.remove(self.identity,running=lambda:False)
            self.assertEqual(self.snapshot(game),before)

    def test_restore_never_overwrites_reinstalled_skin(self):
        game,lib=self.fixture();removed=lib.remove(self.identity,running=lambda:False)
        with patch('packaging_core.preflight',return_value={}):self.tool.install(self.inspected,game,running=lambda:False)
        before=self.snapshot(game,True)
        with self.assertRaisesRegex(PackageError,'已存在'):lib.restore(removed['removal_id'],running=lambda:False)
        self.assertEqual(self.snapshot(game,True),before)

    def test_corrupt_selection_blocks_deletion_without_changing_files(self):
        game,lib=self.fixture();(game/MOD_REL/'selections.json').write_text('{broken');before=self.snapshot(game)
        self.assertEqual(len(lib.installed()),1)
        with self.assertRaises(ValueError):lib.remove(self.identity,running=lambda:False)
        self.assertEqual(self.snapshot(game),before)

    def test_missing_owned_payload_can_still_be_removed_and_restored_as_incomplete(self):
        game,lib=self.fixture();lib.targets(self.identity)[2].unlink()
        self.assertTrue(lib.installed()[0]['managed']);self.assertFalse(lib.installed()[0]['complete'])
        removed=lib.remove(self.identity,running=lambda:False);lib.restore(removed['removal_id'],running=lambda:False)
        self.assertFalse(lib.installed()[0]['complete'])

    def test_malformed_receipt_does_not_break_inventory(self):
        game,lib=self.fixture();save_json(lib.targets(self.identity)[0]/'installed-package.json',123)
        self.assertEqual(len(lib.installed()),1);self.assertFalse(lib.installed()[0]['managed'])

    def test_path_traversal_and_double_underscore_ids(self):
        game,lib=self.fixture();before=self.snapshot(game)
        for identity in ('../outside','sasili__PP0021_su57__../../outside',123):
            with self.assertRaises(PackageError):lib.remove(identity,running=lambda:False)
        for key in ('../outside','bad',123):
            with self.assertRaises(PackageError):lib.restore(key,running=lambda:False)
        self.assertEqual(identity_parts('my__author__PP0021_su57__my__skin'),['my__author','PP0021_su57','my__skin'])
        self.assertEqual(self.snapshot(game),before)

    def test_all_backend_error_and_progress_literals_have_english(self):
        missing=[]
        for name in ('packaging_core.py','library.py','app.py','asset_header.py','compatibility.py','exports.py'):
            tree=ast.parse((PROJECT/name).read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node,ast.Call) and (isinstance(node.func,ast.Name) and node.func.id in ('PackageError','CompatibilityError','progress')):
                    for arg in node.args:
                        for part in ast.walk(arg):
                            if isinstance(part,ast.Constant) and isinstance(part.value,str) and re.search('[\u4e00-\u9fff]',english(part.value)):
                                missing.append((name,part.lineno,part.value))
        self.assertEqual(missing,[])
        self.assertNotRegex(english('正在转换贴图 1/2…'),'[\u4e00-\u9fff]')
        self.assertNotRegex(english('已安装。下次离线启动游戏后，在对应机型的 LIVERY 按钮中选择。'),'[\u4e00-\u9fff]')


if __name__=='__main__':unittest.main(verbosity=2)

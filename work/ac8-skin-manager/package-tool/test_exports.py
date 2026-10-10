"""Desktop export regression checks with real package bytes and dialog responses."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from exports import completed_package, export_with_dialog, save_package
from packaging_core import PackageError, digest


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ac8-export-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / 'jobs'
        self.workspace.mkdir()
        self.source = self.workspace / 'sasili__PP0021_su57__kamome.ac8skin.zip'
        self.source.write_bytes(b'package bytes for save regression')
        self.jobs = {'author': {'kind': 'author', 'state': 'done', 'result': {
            'path': str(self.source), 'bytes': self.source.stat().st_size,
            'sha256': digest(self.source)}}}

    def test_native_save_dialog_exports_and_file_can_be_read_again(self):
        target = self.root / '中文目录'
        target.mkdir()
        for response in (str(target / '中文涂装.ac8skin.zip'), (str(target / 'English.ac8skin.zip'),)):
            window = Mock()
            window.create_file_dialog.return_value = response
            result = export_with_dialog(self.jobs, 'author', self.workspace, window, 30)
            self.assertFalse(result['cancelled'])
            self.assertEqual(Path(result['path']).read_bytes(), self.source.read_bytes())
            self.assertEqual(window.create_file_dialog.call_args.kwargs['save_filename'], self.source.name)

    def test_cancel_then_retry_does_not_require_rebuild(self):
        window = Mock()
        window.create_file_dialog.side_effect = [None, (str(self.root / 'retry.zip'),)]
        self.assertEqual(export_with_dialog(self.jobs, 'author', self.workspace, window, 30), {'cancelled': True})
        self.assertFalse((self.root / 'retry.zip').exists())
        result = export_with_dialog(self.jobs, 'author', self.workspace, window, 30)
        self.assertEqual(digest(result['path']), digest(self.source))

    def test_only_completed_author_jobs_inside_workspace_can_export(self):
        for key in (None, [], 'missing'):
            with self.assertRaises(PackageError):
                completed_package(self.jobs, key, self.workspace)
        for kind, state in (('player', 'done'), ('author', 'working'), ('author', 'error')):
            self.jobs['author'].update(kind=kind, state=state)
            with self.assertRaises(PackageError):
                completed_package(self.jobs, 'author', self.workspace)
        self.jobs['author'].update(kind='author', state='done')
        outside = self.root / self.source.name
        outside.write_bytes(self.source.read_bytes())
        self.jobs['author']['result']['path'] = str(outside)
        with self.assertRaises(PackageError):
            completed_package(self.jobs, 'author', self.workspace)

    def test_changed_or_missing_export_is_detected(self):
        self.source.write_bytes(b'x' * self.source.stat().st_size)
        with self.assertRaises(PackageError):
            completed_package(self.jobs, 'author', self.workspace)
        self.source.unlink()
        with self.assertRaises(PackageError):
            completed_package(self.jobs, 'author', self.workspace)

    def test_source_changes_while_dialog_is_open_are_detected(self):
        target = self.root / 'changed.zip'
        def dialog(*args, **kwargs):
            self.source.write_bytes(b'changed during dialog')
            return (str(target),)
        window = Mock()
        window.create_file_dialog.side_effect = dialog
        with self.assertRaises(PackageError):
            export_with_dialog(self.jobs, 'author', self.workspace, window, 30)
        self.assertFalse(target.exists())

    def test_failed_save_preserves_previous_file_and_removes_temporary(self):
        target = self.root / 'existing.zip'
        target.write_bytes(b'previous download')
        with patch('exports.os.replace', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                save_package(self.source, target)
        self.assertEqual(target.read_bytes(), b'previous download')
        self.assertEqual(list(self.root.glob('.ac8-export-*')), [])

    def test_extension_and_save_to_source(self):
        result = save_package(self.source, self.root / 'name')
        self.assertTrue(result['path'].endswith('name.ac8skin.zip'))
        self.assertEqual(digest(result['path']), digest(self.source))
        self.assertEqual(save_package(self.source, self.source)['path'], str(self.source))


if __name__ == '__main__':
    unittest.main(verbosity=2)

"""Save completed author packages through the desktop file dialog."""
from pathlib import Path
import os
import shutil
import tempfile

from packaging_core import PackageError, digest


def completed_package(jobs, key, workspace):
    job = jobs.get(key) if isinstance(key, str) else None
    if not job or job.get('kind') != 'author' or job.get('state') != 'done':
        raise PackageError('尚未生成涂装包。')
    result = job.get('result', {})
    file = Path(result.get('path', '')).resolve()
    if (not file.is_relative_to(Path(workspace).resolve()) or not file.is_file()
            or not file.name.endswith('.ac8skin.zip')
            or file.stat().st_size != result.get('bytes')):
        raise PackageError('导出文件缺失或已改变，请重新生成涂装包。')
    if result.get('sha256') and digest(file) != result['sha256']:
        raise PackageError('导出文件缺失或已改变，请重新生成涂装包。')
    return file


def save_package(source, chosen):
    """Copy atomically so a failed save leaves an existing destination intact."""
    source, destination = Path(source).resolve(), Path(chosen).resolve()
    if not destination.name.lower().endswith('.zip'):
        destination = destination.with_name(destination.name + '.ac8skin.zip')
    if source == destination:
        return {'cancelled': False, 'path': str(destination), 'bytes': source.stat().st_size}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.ac8-export-', suffix='.tmp',
                                         dir=destination.parent, delete=False) as out:
            temporary = Path(out.name)
            with source.open('rb') as src:
                shutil.copyfileobj(src, out, 1024 * 1024)
            out.flush()
            os.fsync(out.fileno())
        if digest(temporary) != digest(source):
            raise PackageError('保存校验失败，请重试。')
        os.replace(temporary, destination)
        return {'cancelled': False, 'path': str(destination), 'bytes': destination.stat().st_size}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def export_with_dialog(jobs, key, workspace, window, dialog_type, directory=''):
    source = completed_package(jobs, key, workspace)
    chosen = window.create_file_dialog(dialog_type, directory=directory,
                                      save_filename=source.name,
                                      file_types=('AC8 Livery Package (*.zip)',))
    if not chosen:
        return {'cancelled': True}
    # pywebview backends have returned both str and tuple for save dialogs.
    target = chosen if isinstance(chosen, str) else chosen[0]
    return save_package(completed_package(jobs, key, workspace), target)

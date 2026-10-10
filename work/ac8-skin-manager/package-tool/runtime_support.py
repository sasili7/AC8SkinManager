"""Windows paths and window sizing without machine-specific folders."""
from pathlib import Path
import os


def downloads_folder():
    if os.name == 'nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
                value = winreg.QueryValueEx(key, '{374DE290-123F-4565-9164-39C4925E467B}')[0]
            path = Path(os.path.expandvars(value))
            if path.is_dir():
                return str(path)
        except OSError:
            pass
    folder = Path.home() / 'Downloads'
    return str(folder if folder.is_dir() else Path.home())


def fit_window(width, height):
    width, height = max(240, int(width) - 24), max(240, int(height) - 48)
    size = min(600, width), min(820, height)
    return size, (min(400, size[0]), min(400, size[1]))


def desktop_geometry():
    if os.name == 'nt':
        try:
            import ctypes
            from ctypes import wintypes
            ctypes.windll.user32.SetProcessDPIAware()
            area = wintypes.RECT()
            if not ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(area), 0):
                raise OSError('Work area unavailable')
            scale = ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100
            return fit_window((area.right - area.left) / scale, (area.bottom - area.top) / scale)
        except (OSError, AttributeError):
            pass
    return (600, 820), (400, 400)

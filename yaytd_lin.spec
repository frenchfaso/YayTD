# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from build_config import resolve_app_version, write_version_file


APP_VERSION = resolve_app_version()
VERSION_FILE = write_version_file('build/yaytd_version.txt', APP_VERSION)


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('yaytd_logo_64.png', '.'), (VERSION_FILE, '.')] + collect_data_files('sv_ttk'),
    hiddenimports=['PIL._tkinter_finder'] + collect_submodules('yt_dlp'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['darkdetect._mac_detect', 'darkdetect._windows_detect'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='yaytd',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

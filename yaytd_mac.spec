# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('yaytd_logo_64.png', '.')],
    hiddenimports=['PIL._tkinter_finder'] + collect_submodules('yt_dlp'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='yaytd',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['yaytd.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=True,
    upx_exclude=[],
    name='yaytd',
)
app = BUNDLE(
    coll,
    name='yaytd.app',
    icon='yaytd.icns',
    bundle_identifier=None,
    info_plist={
        'NSRequiresAquaSystemAppearance': True,
    },
)

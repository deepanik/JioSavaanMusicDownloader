# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['JioMusicDLD.py'],
    pathex=[],
    binaries=[],
    datas=[('app_icon.ico', '.'), ('assets/*', 'assets')],
    hiddenimports=['requests', 'mutagen', 'sanitize_filename'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'PIL', 'pandas'],
    noarchive=True,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [('v', None, 'OPTION')],
    name='JioSaavn_MUSIC_Downloader',
    debug=True,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app_icon.ico'],
)

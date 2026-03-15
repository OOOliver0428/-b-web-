# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['..\\run.py'],
    pathex=[],
    binaries=[],
    datas=[('D:\\CODE\\bilibili-mod-tool/app/static', 'app/static')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['D:\\CODE\\bilibili-mod-tool\\build\\runtime_hook.py'],
    excludes=[],
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
    name='B站房管工具',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

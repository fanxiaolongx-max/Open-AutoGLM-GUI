# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['sqlite3', 'email.mime.image', 'PySide6', 'PySide6.QtCore', 'fastapi', 'fastapi.middleware.cors', 'starlette', 'uvicorn', 'pydantic']
hiddenimports += collect_submodules('fastapi')
hiddenimports += collect_submodules('starlette')
hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('email')


a = Analysis(
    ['run_web.py'],
    pathex=[],
    binaries=[],
    datas=[('phone_agent', 'phone_agent'), ('web_app', 'web_app'), ('gui_app', 'gui_app')],
    hiddenimports=hiddenimports,
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
    a.binaries,
    a.datas,
    [],
    name='Open-AutoGLM-GUI-web-test',
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

# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app\\main_pyqt6.py'],
    pathex=[],
    binaries=[],
    datas=[('app/resources', 'app/resources')],
    hiddenimports=['qt_material', 'qasync', 'PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineWidgets', 'PyQt6.QtWebEngine', 'PyQt6.QtMultimedia'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['build_hooks/force_pyqt6.py'],
    excludes=['PyQt5', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets', 'PySide2', 'PySide6'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PeachClient',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app\\resources\\icons\\custom\\main app pixels.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PeachClient',
)

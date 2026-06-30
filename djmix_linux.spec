# djmix_linux.spec — PyInstaller spec para DJ Mix Player (Linux / Flatpak)
# Para buildar: pyinstaller djmix_linux.spec

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[
        ('/usr/lib/x86_64-linux-gnu/libportaudio.so.2.0.0', '.'),
        ('/usr/lib/x86_64-linux-gnu/libsndfile.so.1.0.37', '.'),
    ],
    datas=[
        ('fonts',      'fonts'),
        ('assets',     'assets'),
        ('version.py', '.'),
        ('updater.py', '.'),
    ],
    hiddenimports=[
        'sounddevice',
        'soundfile',
        'cffi',
        '_cffi_backend',
        'numpy',
        'pygame',
        'pygame.mixer',
        'pygame.sndarray',
        'mutagen',
        'mutagen.mp3',
        'mutagen.flac',
        'mutagen.mp4',
        'mutagen.ogg',
        'mutagen.wave',
        'urllib.request',
        'version',
        'updater',
        'pulsectl',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['rthook_sounddevice.py'],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DJMixPlayer',
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DJMixPlayer',
)

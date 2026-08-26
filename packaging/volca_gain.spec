# -*- mode: python ; coding: utf-8 -*-
# PyInstaller : construit VolcaGain.exe (fenetre Kivy, sans console).
#   pyinstaller packaging/volca_gain.spec --noconfirm

import os
from kivy_deps import sdl2, glew

block_cipher = None

a = Analysis(
    ['../main.py'],
    pathex=[os.path.abspath('.')],
    binaries=[],
    datas=([('../assets/logo.png', 'assets'),
            ('../assets/icon.png', 'assets')]
           + ([('../native/syro.dll', '.')]
              if os.path.isfile('native/syro.dll') else [])),
    hiddenimports=['volca', 'volca.audio', 'volca.batch', 'volca.project', 'volca.syro', 'volca.tips', 'volca.reglages', 'volca.etat', 'volca.kit', 'volca.pattern', 'volca.librarian', 'volca.morceau', 'volca.bibliotheque'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['numpy', 'scipy', 'matplotlib', 'tkinter'],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    *[Tree(p) for p in (sdl2.dep_bins + glew.dep_bins)],
    name="MOC'TA BASS",
    debug=False,
    strip=False,
    upx=False,   # upx ralentit fortement le build pour peu de gain
    console=False,
    icon='../assets/icon.ico',
)

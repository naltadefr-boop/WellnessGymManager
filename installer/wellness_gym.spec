# -*- mode: python ; coding: utf-8 -*-
# Construction de l'exécutable Windows :  pyinstaller installer\wellness_gym.spec --noconfirm
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

RACINE = os.path.abspath(os.path.join(SPECPATH, ".."))
sys.path.insert(0, RACINE)

hidden = (collect_submodules("gym") + collect_submodules("wellness_gym") + collect_submodules("django.contrib")
          + collect_submodules("waitress") + collect_submodules("whitenoise")
          + ["django.template.loaders.app_directories", "django.templatetags.static"])
datas = (collect_data_files("gym") + collect_data_files("reportlab")
         + collect_data_files("django", includes=["**/*.html", "**/*.txt", "**/*.json", "**/locale/fr/**"]))

a = Analysis([os.path.join(RACINE, "lancer.py")], pathex=[RACINE], datas=datas, hiddenimports=hidden, noarchive=False,
             excludes=["tkinter", "matplotlib", "numpy", "playwright"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="WellnessGym", console=True,
          icon=os.path.join(RACINE, "gym", "static", "gym", "img", "wellness.ico"))
coll = COLLECT(exe, a.binaries, a.datas, name="WellnessGym")

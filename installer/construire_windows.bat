@echo off
chcp 65001 >nul
REM Construit l'exécutable et l'installateur Windows (à lancer sur un PC Windows avec Python 3.11+).
cd /d "%~dp0\.."
python -m venv .venv-build || goto erreur
call .venv-build\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller || goto erreur
python manage.py test gym || goto erreur
pyinstaller installer\wellness_gym.spec --noconfirm --distpath dist --workpath build || goto erreur
echo.
echo Executable cree dans dist\WellnessGym\WellnessGym.exe
where iscc >nul 2>nul && (iscc installer\setup.iss && echo Installateur cree dans installer\Output) || echo Installez Inno Setup 6 (jrsoftware.org) puis lancez : iscc installer\setup.iss
pause
exit /b 0
:erreur
echo ECHEC de la construction.
pause
exit /b 1

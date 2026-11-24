@echo off
chcp 65001 >nul
title Wellness Gym Manager - NE PAS FERMER
cd /d "%~dp0"
REM Premier lancement : préparation automatique (connexion Internet nécessaire une seule fois)
if not exist ".venv\Scripts\python.exe" (
  echo Premier lancement : installation des composants, patientez...
  python -m venv .venv || (echo Python 3.11 ou plus recent est requis : https://www.python.org/downloads/ & pause & exit /b 1)
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || (echo Echec de l'installation des composants. & pause & exit /b 1)
)
".venv\Scripts\python.exe" lancer.py %*
pause

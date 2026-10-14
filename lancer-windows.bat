@echo off
REM Lance le Transcripteur audio sur Windows (installe tout au premier lancement).
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3 est introuvable. Installez-le depuis https://www.python.org/downloads/ puis relancez.
  pause
  exit /b 1
)

if not exist ".venv" (
  echo Premiere installation, quelques minutes...
  python -m venv .venv || exit /b 1
  .venv\Scripts\python.exe -m pip install --upgrade pip
  .venv\Scripts\python.exe -m pip install -r requirements.txt || exit /b 1
)

echo Demarrage : l'application s'ouvre dans votre navigateur (http://localhost:8501).
.venv\Scripts\python.exe -m streamlit run app.py

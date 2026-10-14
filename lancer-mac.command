#!/bin/bash
# Lance le Transcripteur audio sur macOS (installe tout au premier lancement).
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 est introuvable. Installez-le depuis https://www.python.org/downloads/ puis relancez."
  read -r -p "Appuyez sur Entrée pour fermer."
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Première installation (quelques minutes)..."
  python3 -m venv .venv || exit 1
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt || exit 1
fi

echo "Démarrage : l'application s'ouvre dans votre navigateur (http://localhost:8501)."
.venv/bin/python -m streamlit run app.py --server.headless false

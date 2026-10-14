"""Point d'entrée de la version installable (PyInstaller) : démarre Streamlit sur app.py."""
import os
import sys

# Importés ici pour que PyInstaller les embarque (app.py est chargé dynamiquement par Streamlit).
import core.exporters  # noqa: F401
import core.languages  # noqa: F401
import core.transcriber  # noqa: F401
import core.translator  # noqa: F401
import deep_translator  # noqa: F401
import fpdf  # noqa: F401
import faster_whisper  # noqa: F401


def main():
    from streamlit.web import cli as stcli

    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    os.chdir(base)
    if base not in sys.path:
        sys.path.insert(0, base)
    sys.argv = [
        "streamlit", "run", os.path.join(base, "app.py"),
        "--global.developmentMode=false",
        f"--server.headless={os.environ.get('TRANSCRIPTEUR_HEADLESS', 'false')}",
        f"--server.port={os.environ.get('TRANSCRIPTEUR_PORT', '8501')}",
        "--browser.gatherUsageStats=false",
    ]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()

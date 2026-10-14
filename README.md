# Transcripteur audio multilingue

Transcrit des fichiers audio (MP3, WAV, M4A, FLAC, OGG) en texte, dans 25 langues, avec traduction optionnelle et export TXT, SRT ou PDF. La transcription tourne **en local** sur votre ordinateur (Faster-Whisper) ; seule la traduction utilise Internet (Google Translate).

## Utiliser en ligne (version hébergée)

L'application peut être hébergée sur [Streamlit Community Cloud](https://share.streamlit.io) : connectez-vous avec GitHub, « Create app », dépôt `antonindgl/transcripteur-audio`, branche `main`, fichier `app.py`, Python 3.12.

- La mémoire gratuite est limitée : utilisez les modèles `tiny` ou `base`.
- Code d'accès optionnel : dans « Advanced settings » → « Secrets », collez une section `[access]` avec `salt`, `iterations` et `hash` (empreinte PBKDF2-SHA256 du code, voir `core/access.py`). Sans cette section, l'accès est libre.

## Télécharger

**[Page des téléchargements (Releases)](../../releases/latest)**

| Fichier | Pour qui |
|---|---|
| `Transcripteur-Windows.zip` | Windows, sans rien installer : décompresser puis lancer `Installer.bat` |
| `Transcripteur-Python-Windows-Mac.zip` | Windows et Mac, avec Python 3.9+ |

Windows peut afficher « Windows a protégé votre ordinateur » car le programme n'est pas signé numériquement : cliquer sur « Informations complémentaires » puis « Exécuter quand même ».

Au premier envoi d'un audio, le modèle Whisper se télécharge (environ 500 Mo pour « small »).

## Lancer depuis le code

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (Mac/Linux : source .venv/bin/activate)
pip install -r requirements.txt
streamlit run app.py
```

Sur Mac : `bash lancer-mac.command`. Sur Windows : `lancer-windows.bat`.

## Structure

```
app.py              interface Streamlit
launcher.py         point d'entrée de la version installable (PyInstaller)
core/               transcription, traduction, exports, langues
assets/             style, icône
```

## Limites

- La traduction passe par un accès non officiel à Google Translate : elle peut être limitée en débit sur les longs fichiers.
- Le PDF des langues non latines (chinois, japonais, arabe, hindi…) demande une police `.ttf` compatible dans `assets/fonts/`.
- Sur Mac, la transcription utilise le processeur : préférer les modèles `tiny`, `base` ou `small`.

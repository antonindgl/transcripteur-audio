"""Interface Streamlit : transcription multilingue, traduction, export."""
import json
import os
import tempfile
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from core import exporters
from core.access import require_access
from core.languages import LANGUAGES, label
from core.transcriber import MODEL_SIZES, SUPPORTED_EXTENSIONS, load_model, transcribe
from core.translator import translate_result

st.set_page_config(
    page_title="Transcripteur audio", page_icon="🎙️", layout="wide",
    initial_sidebar_state="collapsed",
)

CSS = (Path(__file__).parent / "assets" / "style.css").read_text(encoding="utf-8")
WAVE_HEIGHTS = [30, 52, 78, 44, 92, 60, 84, 40, 96, 66, 36, 88, 54, 32, 72, 48]
SHOWN_LANGS = ["en", "fr", "es", "zh", "de", "ja", "ar", "pt", "ru", "hi", "ko", "tr"]


def html(block: str):
    """Affiche du HTML sans que Markdown le prenne pour du code (pas d'indentation)."""
    st.markdown("\n".join(l.strip() for l in block.splitlines() if l.strip()), unsafe_allow_html=True)


@st.cache_resource(show_spinner="Chargement du modèle (téléchargement au premier usage)…")
def get_model(size: str):
    return load_model(size)


def copy_button(text: str):
    """Bouton de copie dans le presse-papiers (JS côté navigateur)."""
    safe = json.dumps(text).replace("</", "<\\/")
    components.html(
        f"""
        <button id="b" style="padding:10px 18px;border-radius:12px;border:0;font-family:sans-serif;
          background:#6f8fd6;color:#0b0f17;font-weight:700;cursor:pointer;font-size:14px">Copier le texte</button>
        <script>
        document.getElementById('b').onclick = async () => {{
          try {{ await navigator.clipboard.writeText({safe}); document.getElementById('b').innerText = 'Copié'; }}
          catch (e) {{ document.getElementById('b').innerText = 'Sélectionnez le texte'; }}
        }};
        </script>""",
        height=50,
    )


def show_result(res, title: str, key: str):
    st.subheader(title)
    copy_button(res.text)
    st.text_area("Texte", res.text, height=350, key=f"ta_{key}", label_visibility="collapsed")
    c1, c2, c3 = st.columns(3)
    c1.download_button("TXT", exporters.to_txt(res), f"{key}.txt", "text/plain", key=f"t_{key}")
    c2.download_button("SRT", exporters.to_srt(res), f"{key}.srt", "application/x-subrip", key=f"s_{key}")
    c3.download_button("PDF", exporters.to_pdf(res, title), f"{key}.pdf", "application/pdf", key=f"p_{key}")


# ---------------------------------------------------------------- Page : en-tête
st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
require_access()
bars = "".join(f'<span style="--h:{h}%;--d:{i * 0.11:.2f}s"></span>' for i, h in enumerate(WAVE_HEIGHTS))
html(f"""
<div class="nav">
<div class="brand"><i><b></b><b></b><b></b></i>Transcripteur</div>
<div class="nav-links"><a href="#fonctions">Fonctions</a><a href="#outil">Essayer</a><a href="#langues">Langues</a></div>
</div>
<div class="hero">
<div>
<h1>Toutes les voix du monde, <em>en texte.</em></h1>
<p class="lead">Importez un enregistrement, laissez l'IA le transcrire sur votre ordinateur, traduisez-le si besoin et exportez en TXT, SRT ou PDF.</p>
<div class="cta"><a class="btn" href="#outil">Transcrire un fichier</a><a class="btn ghost" href="#fonctions">Voir les fonctions</a></div>
</div>
<div class="wave" role="img" aria-label="Onde sonore animée">{bars}</div>
</div>
<div class="sec" id="fonctions">
<p class="eyebrow">Fonctions</p>
<h2>De l'audio au texte exportable</h2>
<div class="grid4">
<div class="card"><span class="tag">MP3 · WAV · M4A · FLAC · OGG</span><h3>Importer</h3><p>Glissez un fichier audio dans les formats courants. Aucune conversion préalable.</p></div>
<div class="card"><span class="tag">AUTO OU MANUEL</span><h3>Détecter la langue</h3><p>La langue est reconnue automatiquement, avec un pourcentage de confiance. Vous pouvez aussi l'imposer.</p></div>
<div class="card"><span class="tag">OPTION</span><h3>Traduire</h3><p>Traduction vers une autre langue, segment par segment, pour garder les horodatages des sous-titres.</p></div>
<div class="card"><span class="tag">TXT · SRT · PDF</span><h3>Exporter</h3><p>Texte brut, sous-titres synchronisés ou document PDF, et un bouton pour copier en un clic.</p></div>
</div>
</div>
<div class="sec" id="outil">
<p class="eyebrow">Essayer</p>
<h2>Une barre de progression, puis le texte</h2>
<p class="sub">Choisissez vos réglages, importez un fichier audio et lancez la transcription.</p>
</div>
""")

# ---------------------------------------------------------------- Outil
col1, col2, col3 = st.columns(3)
model_size = col1.selectbox(
    "Modèle Whisper", MODEL_SIZES, index=1,
    help="Plus grand = plus précis mais plus lent. 'base' est rapide, 'small' est un bon "
         "compromis. 'medium' et 'large-v3' demandent beaucoup de mémoire.",
)
lang_choice = col2.selectbox(
    "Langue de l'audio", ["auto"] + list(LANGUAGES),
    format_func=lambda c: "Détection automatique" if c == "auto" else label(c),
)
target = col3.selectbox("Traduire vers", ["—"] + list(LANGUAGES),
                        format_func=lambda c: "Ne pas traduire" if c == "—" else label(c))
translate_on = target != "—"

uploaded = st.file_uploader("Importer un fichier audio", type=list(SUPPORTED_EXTENSIONS))

if uploaded:
    st.audio(uploaded)
    if st.button("Lancer la transcription", type="primary"):
        suffix = os.path.splitext(uploaded.name)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.getbuffer())
            path = tmp.name
        try:
            model = get_model(model_size)
            bar = st.progress(0.0, text="Transcription en cours…")
            result = transcribe(
                model, path, None if lang_choice == "auto" else lang_choice,
                lambda p: bar.progress(p, text=f"Transcription… {int(p * 100)} %"),
            )
            translated = None
            if translate_on and result.segments:
                bar.progress(0.0, text="Traduction en cours…")
                translated = translate_result(
                    result, target,
                    lambda p: bar.progress(p, text=f"Traduction… {int(p * 100)} %"),
                )
            bar.progress(1.0, text="Terminé")
            st.session_state["result"] = (result, translated, os.path.splitext(uploaded.name)[0])
        except Exception as e:
            st.error(f"Erreur : {e}")
        finally:
            os.remove(path)

if "result" in st.session_state:
    result, translated, stem = st.session_state["result"]
    if not result.segments:
        st.warning("Aucune parole détectée dans ce fichier.")
    else:
        st.info(f"Langue détectée : **{label(result.language)}** "
                f"(confiance {result.language_probability:.0%}) · durée {result.duration:.0f} s")
        if translated:
            tab1, tab2 = st.tabs(["Original", f"Traduction ({label(translated.language)})"])
            with tab1:
                show_result(result, "Transcription originale", stem)
            with tab2:
                show_result(translated, "Traduction", f"{stem}_{translated.language}")
        else:
            show_result(result, "Transcription", stem)

# ---------------------------------------------------------------- Langues + pied de page
chips = "".join(f"<span>{LANGUAGES[c]}</span>" for c in SHOWN_LANGS)
html(f"""
<div class="sec" id="langues" style="margin-top:72px">
<p class="eyebrow">Langues</p>
<h2>{len(LANGUAGES)} langues, en transcription comme en traduction</h2>
<div class="langs">{chips}<span class="more">+ {len(LANGUAGES) - len(SHOWN_LANGS)} autres</span></div>
</div>
<div class="foot"><span>Transcripteur audio multilingue</span><span>Faster-Whisper · deep-translator · fpdf2 · La transcription reste sur votre ordinateur</span></div>
""")

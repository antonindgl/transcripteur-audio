"""Interface Streamlit : transcription multilingue, traduction, export."""
import faulthandler
import json
import sys
import time
import uuid
from pathlib import Path

faulthandler.enable()  # en cas de plantage natif, la trace apparaît dans les journaux

import streamlit as st
import streamlit.components.v1 as components

from core import exporters, jobs
from core.access import require_access
from core.browser_translate import translate_widget
from core.languages import LANGUAGES, label
from core.transcriber import MODEL_SIZES, SUPPORTED_EXTENSIONS

st.set_page_config(
    page_title="Transcripteur audio", page_icon="🎙️", layout="wide",
    initial_sidebar_state="collapsed",
)

CSS = (Path(__file__).parent / "assets" / "style.css").read_text(encoding="utf-8")
WAVE_HEIGHTS = [30, 52, 78, 44, 92, 60, 84, 40, 96, 66, 36, 88, 54, 32, 72, 48]
SHOWN_LANGS = ["en", "fr", "es", "zh", "de", "ja", "ar", "pt", "ru", "hi", "ko", "tr"]
# Hébergement gratuit (Streamlit Community Cloud) : ~1 Go de mémoire, seuls les petits modèles tiennent.
ON_CLOUD = jobs.ON_CLOUD
AVAILABLE_MODELS = [m for m in MODEL_SIZES if m in ("tiny", "base")] if ON_CLOUD else MODEL_SIZES
ACTIVE = ("queued", "running", "translating")


def html(block: str):
    """Affiche du HTML sans que Markdown le prenne pour du code (pas d'indentation)."""
    st.markdown("\n".join(l.strip() for l in block.splitlines() if l.strip()), unsafe_allow_html=True)


def fmt_duration(seconds: float) -> str:
    seconds = int(max(seconds, 0))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h} h {m:02d} min" if h else f"{m} min {s:02d} s"


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


def new_transcription():
    st.query_params.clear()
    st.session_state.pop("job_id", None)


# ---------------------------------------------------------------- Suivi d'un travail
def job_progress_ui(job):
    stage = "Traduction" if job.status == "translating" else "Transcription"
    pct = int(job.progress * 100)
    st.progress(min(max(job.progress, 0.0), 1.0), text=f"{stage}… {pct} %")
    elapsed = time.time() - job.created
    info = [f"Écoulé : {fmt_duration(elapsed)}"]
    if job.duration:
        info.insert(0, f"Durée de l'audio : {fmt_duration(job.duration)}")
    if job.status == "running" and job.progress > 0.03:
        info.append(f"Reste environ : {fmt_duration(elapsed * (1 - job.progress) / job.progress)}")
    st.caption(" · ".join(info))
    if job.segments:
        recent = "\n".join(s[2] for s in job.segments[-12:])
        st.text_area("Dernières lignes transcrites", recent, height=220, disabled=True,
                     key=f"live_{job.id}")


@st.fragment(run_every=3)
def live_panel(job_id: str):
    """Se rafraîchit toutes les 3 s tant que le travail est actif, puis relance la page."""
    job = jobs.get_job(job_id)
    if job is None or job.status not in ACTIVE:
        st.rerun()
        return
    job_progress_ui(job)
    if st.button("Annuler", key=f"cancel_{job.id}"):
        jobs.cancel_job(job)


def finished_panel(job):
    # Une transcription terminée reste valable même si une traduction côté serveur a échoué.
    transcribed = job.status == "done" or (
        job.status == "error" and job.progress >= 0.999 and job.segments
    )
    if transcribed:
        if not job.segments:
            st.warning("Aucune parole détectée dans ce fichier.")
        else:
            st.success(f"Transcription terminée en {fmt_duration(job.updated - job.created)}.")
            st.info(f"Langue détectée : **{label(job.detected_language)}** "
                    f"(confiance {job.probability:.0%}) · durée {fmt_duration(job.duration)}")
            stem = Path(job.name).stem
            if job.translated:
                tab1, tab2 = st.tabs(["Original", f"Traduction ({label(job.target)})"])
                with tab1:
                    show_result(job.result(), "Transcription originale", stem)
                with tab2:
                    show_result(job.result(True), "Traduction", f"{stem}_{job.target}")
            else:
                show_result(job.result(), "Transcription", stem)
                st.subheader("Traduire")
                if job.translation_error or job.status == "error":
                    st.caption("La traduction automatique du serveur n'a pas abouti. "
                               "Utilisez le traducteur ci-dessous : il fonctionne depuis votre navigateur.")
                else:
                    st.caption("Choisissez la langue, puis cliquez sur « Traduire ». "
                               "La traduction se fait depuis votre navigateur.")
                translate_widget(job.segments, job.detected_language, job.target or "en", stem)
    elif job.status == "cancelled":
        st.warning("Transcription annulée.")
        if job.segments:
            show_result(job.result(), "Texte partiel", Path(job.name).stem + "_partiel")
    else:  # interrompu ou en erreur
        if job.status == "error":
            st.error(f"Erreur : {job.error}")
        else:
            st.warning("Le traitement a été interrompu (redémarrage du serveur).")
        if job.segments:
            st.caption(f"{int(job.progress * 100)} % déjà transcrit, conservé.")
        if jobs.can_resume(job):
            if st.button("Reprendre là où ça s'est arrêté", type="primary"):
                jobs.resume_job(job)
                st.rerun()
        if job.segments:
            show_result(job.result(), "Texte partiel", Path(job.name).stem + "_partiel")
    st.button("Nouvelle transcription", on_click=new_transcription, key=f"new_{job.id}")


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
<div class="card"><span class="tag">MP3 · WAV · M4A · FLAC · OGG</span><h3>Importer</h3><p>Glissez un fichier audio dans les formats courants, même d'une heure ou plus.</p></div>
<div class="card"><span class="tag">AUTO OU MANUEL</span><h3>Détecter la langue</h3><p>La langue est reconnue automatiquement, avec un pourcentage de confiance. Vous pouvez aussi l'imposer.</p></div>
<div class="card"><span class="tag">OPTION</span><h3>Traduire</h3><p>Traduction vers une autre langue, segment par segment, pour garder les horodatages des sous-titres.</p></div>
<div class="card"><span class="tag">TXT · SRT · PDF</span><h3>Exporter</h3><p>Texte brut, sous-titres synchronisés ou document PDF, et un bouton pour copier en un clic.</p></div>
</div>
</div>
<div class="sec" id="outil">
<p class="eyebrow">Essayer</p>
<h2>Une barre de progression, puis le texte</h2>
<p class="sub">Choisissez vos réglages, importez un fichier audio et lancez la transcription. Le travail continue en arrière-plan : vous pouvez fermer la page et revenir avec la même adresse.</p>
</div>
""")

# ---------------------------------------------------------------- Outil
job_id = st.query_params.get("job") or st.session_state.get("job_id")
job = jobs.get_job(job_id) if job_id else None

if job is not None:
    st.session_state["job_id"] = job.id
    st.query_params["job"] = job.id
    st.markdown(f"**Fichier :** {job.name}")
    if job.status in ACTIVE:
        st.info("Vous pouvez fermer cette page : le travail continue. Gardez l'adresse de cette page "
                "pour revenir voir le résultat.")
        live_panel(job.id)
    else:
        finished_panel(job)
else:
    if job_id:
        st.warning("Ce travail est introuvable (le serveur a peut-être été réinitialisé).")
        st.query_params.clear()
    col1, col2, col3 = st.columns(3)
    model_size = col1.selectbox(
        "Modèle Whisper", AVAILABLE_MODELS, index=AVAILABLE_MODELS.index("base"),
        help="Plus grand = plus précis mais plus lent. 'base' est rapide, 'small' est un bon "
             "compromis. 'medium' et 'large-v3' demandent beaucoup de mémoire.",
    )
    lang_choice = col2.selectbox(
        "Langue de l'audio", ["auto"] + list(LANGUAGES),
        format_func=lambda c: "Détection automatique" if c == "auto" else label(c),
    )
    target = col3.selectbox("Traduire vers", ["—"] + list(LANGUAGES),
                            format_func=lambda c: "Ne pas traduire" if c == "—" else label(c))

    uploaded = st.file_uploader(
        "Importer un fichier audio", type=list(SUPPORTED_EXTENSIONS),
        help="Pour une heure d'audio ou plus, préférez MP3 ou M4A (le WAV est très volumineux).",
    )
    if uploaded:
        st.audio(uploaded)
        if st.button("Lancer la transcription", type="primary"):
            jobs.JOBS_DIR.mkdir(parents=True, exist_ok=True)
            path = jobs.JOBS_DIR / f"up_{uuid.uuid4().hex[:10]}{Path(uploaded.name).suffix.lower()}"
            path.write_bytes(uploaded.getbuffer())
            new_job = jobs.start_job(
                str(path), uploaded.name, model_size,
                None if lang_choice == "auto" else lang_choice,
                None if target == "—" else target,
            )
            print(f"[transcripteur] travail {new_job.id} lancé : {uploaded.name}, modèle {model_size}",
                  file=sys.stderr, flush=True)
            st.session_state["job_id"] = new_job.id
            st.query_params["job"] = new_job.id
            st.rerun()

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

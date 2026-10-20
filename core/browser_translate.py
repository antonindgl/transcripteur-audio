"""Traduction exécutée dans le navigateur de l'utilisateur.

Sur l'hébergement gratuit, Google bloque les requêtes venant des serveurs partagés
(« too many requests »). Le navigateur de l'utilisateur, lui, utilise sa propre adresse :
la traduction passe. Le widget traduit par lots, affiche la progression et propose
la copie, le téléchargement TXT et SRT.
"""
from __future__ import annotations

import json

import streamlit.components.v1 as components

from .languages import LANGUAGES, translate_code

_TEMPLATE = r"""
<style>
  :root { color-scheme: dark; }
  body { margin:0; font-family: 'DM Sans', system-ui, sans-serif; color:#e6eaf2; background:transparent; }
  .row { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin-bottom:12px; }
  select, button { font:inherit; border-radius:12px; padding:10px 16px; border:1px solid #263147;
    background:#121826; color:#e6eaf2; }
  button { cursor:pointer; font-weight:700; }
  button.primary { background:#6f8fd6; color:#0b0f17; border-color:#6f8fd6; }
  button:disabled { opacity:.5; cursor:default; }
  .bar { height:12px; border-radius:99px; background:#263147; overflow:hidden; margin:10px 0 6px; }
  .bar b { display:block; height:100%; width:0; background:linear-gradient(90deg,#6f8fd6,#9a85d8); }
  #msg { font-size:14px; color:#9aa6bd; min-height:20px; }
  #msg.err { color:#ff8a8a; }
  textarea { width:100%; box-sizing:border-box; min-height:300px; border-radius:14px; padding:14px;
    background:#121826; color:#e6eaf2; border:1px solid #263147; font:15px/1.6 inherit; }
</style>
<div class="row">
  <select id="lang" aria-label="Langue de traduction"></select>
  <button id="go" class="primary">Traduire</button>
</div>
<div class="bar"><b id="fill"></b></div>
<div id="msg">La traduction se fait depuis votre navigateur et peut prendre quelques minutes.</div>
<textarea id="out" readonly placeholder="La traduction apparaîtra ici."></textarea>
<div class="row" style="margin-top:12px">
  <button id="copy" disabled>Copier la traduction</button>
  <button id="dltxt" disabled>TXT</button>
  <button id="dlsrt" disabled>SRT</button>
</div>
<script>
const D = __DATA__;
const $ = id => document.getElementById(id);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const sel = $('lang');
for (const [code, name] of Object.entries(D.languages)) sel.add(new Option(name + ' (' + code + ')', code));
sel.value = D.target;
let lines = null, lastTarget = D.target;

function setMsg(t, err) { $('msg').textContent = t; $('msg').className = err ? 'err' : ''; }

async function call(text, tl) {
  for (let attempt = 0; attempt < 6; attempt++) {
    const r = await fetch('https://translate.googleapis.com/translate_a/single?client=gtx&dt=t&sl=' +
      encodeURIComponent(D.source) + '&tl=' + encodeURIComponent(tl), {
      method: 'POST',
      headers: {'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'},
      body: 'q=' + encodeURIComponent(text)
    });
    if (r.ok) { const j = await r.json(); return j[0].map(x => x[0]).join(''); }
    if (r.status === 429 || r.status >= 500) { await sleep(1500 * (attempt + 1)); continue; }
    throw new Error('Erreur ' + r.status);
  }
  throw new Error('Google limite les requêtes : réessayez dans quelques minutes.');
}

function groups(texts) {
  const out = []; let cur = [], size = 0;
  texts.forEach((t, i) => {
    if (cur.length && (size + t.length > 2500 || cur.length >= 40)) { out.push(cur); cur = []; size = 0; }
    cur.push(i); size += t.length + 1;
  });
  if (cur.length) out.push(cur);
  return out;
}

function srtTime(s) {
  const ms = Math.round(s * 1000), h = Math.floor(ms / 3600000), m = Math.floor(ms % 3600000 / 60000),
        sec = Math.floor(ms % 60000 / 1000), z = ms % 1000, p = (n, w = 2) => String(n).padStart(w, '0');
  return p(h) + ':' + p(m) + ':' + p(sec) + ',' + p(z, 3);
}

function buildSrt() {
  return D.segments.map((s, i) => (i + 1) + '\n' + srtTime(s[0]) + ' --> ' + srtTime(s[1]) + '\n' + lines[i] + '\n').join('\n');
}

function download(name, text, type) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], {type: type + ';charset=utf-8'}));
  a.download = name; document.body.appendChild(a); a.click(); a.remove();
}

$('go').onclick = async () => {
  const tl = sel.value; lastTarget = tl;
  $('go').disabled = true; ['copy', 'dltxt', 'dlsrt'].forEach(i => $(i).disabled = true);
  $('out').value = ''; $('fill').style.width = '0%';
  const texts = D.segments.map(s => s[2].replace(/\s+/g, ' ').trim());
  const result = new Array(texts.length).fill('');
  try {
    let done = 0;
    for (const g of groups(texts)) {
      const part = (await call(g.map(i => texts[i]).join('\n'), tl)).split('\n');
      if (part.length === g.length) { g.forEach((i, k) => result[i] = part[k].trim() || texts[i]); }
      else { for (const i of g) { result[i] = (await call(texts[i], tl)).trim() || texts[i]; await sleep(300); } }
      done += g.length;
      $('fill').style.width = Math.round(done / texts.length * 100) + '%';
      setMsg('Traduction… ' + Math.round(done / texts.length * 100) + ' %');
      $('out').value = result.filter(Boolean).join('\n');
      await sleep(350);
    }
    lines = result; setMsg('Traduction terminée.');
    ['copy', 'dltxt', 'dlsrt'].forEach(i => $(i).disabled = false);
  } catch (e) {
    setMsg(e.message + ' Le texte déjà traduit reste affiché.', true);
    lines = result; ['copy', 'dltxt'].forEach(i => $(i).disabled = false);
  }
  $('go').disabled = false;
};
$('copy').onclick = async () => {
  try { await navigator.clipboard.writeText($('out').value); setMsg('Copié.'); }
  catch (e) { $('out').select(); setMsg('Sélectionnez le texte et copiez-le (Ctrl+C).'); }
};
$('dltxt').onclick = () => download(D.name + '_' + lastTarget + '.txt', lines.join('\n'), 'text/plain');
$('dlsrt').onclick = () => download(D.name + '_' + lastTarget + '.srt', buildSrt(), 'application/x-subrip');
</script>
"""


def translate_widget(segments: list, source: str, target: str, name: str, height: int = 640) -> None:
    """Affiche le widget de traduction dans le navigateur (segments = [[début, fin, texte], ...])."""
    data = {
        "segments": segments,
        "source": translate_code(source) if source else "auto",
        "target": translate_code(target or "en"),
        "languages": {translate_code(c): n for c, n in LANGUAGES.items()},
        "name": name,
    }
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    components.html(_TEMPLATE.replace("__DATA__", payload), height=height, scrolling=True)

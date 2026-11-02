"""API HTTP (FastAPI) + pagină web minimă. Ascultă doar pe localhost prin compose."""
from __future__ import annotations

import threading

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from . import __version__
from .config import Settings, load_settings
from .llm import LLM
from .provider import OddsProvider, ProviderError
from .service import suggest

PAGE = """<!doctype html>
<html lang="ro"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Odds Agent</title>
<style>
:root{color-scheme:light dark;--bg:#fff;--fg:#1a1a1a;--muted:#666;--card:#f4f5f7;--line:#d9dce1;--acc:#0b6bcb}
@media (prefers-color-scheme:dark){:root{--bg:#14161a;--fg:#e8e8e8;--muted:#9aa0a6;--card:#1d2026;--line:#323741;--acc:#5aa2f0}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}
main{max-width:760px;margin:0 auto;padding:24px 16px}
h1{font-size:1.4rem;margin:0 0 4px}.muted{color:var(--muted);font-size:.9rem}
form{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:20px 0}
label{display:flex;flex-direction:column;font-size:.85rem;color:var(--muted);gap:4px}
input,select{padding:8px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);font-size:1rem}
button{padding:10px 16px;border:0;border-radius:6px;background:var(--acc);color:#fff;font-size:1rem;cursor:pointer;align-self:end}
button:disabled{opacity:.6;cursor:wait}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:14px 0}
.head{display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px;font-weight:600}
.leg{display:flex;justify-content:space-between;gap:12px;padding:6px 0;border-top:1px solid var(--line)}
.leg:first-of-type{margin-top:10px}.leg small{color:var(--muted)}
.warn{border-left:4px solid var(--acc);padding:8px 12px;margin:16px 0;font-size:.9rem}
</style></head><body><main>
<h1>Odds Agent</h1>
<div class="muted">Bilete cu cotă țintă, calculate din cotele reale ale caselor.</div>
<form id="f">
<label>Cotă țintă<input name="target" type="number" step="0.05" min="1.2" max="10" value="2.0"></label>
<label>Max. meciuri<select name="max_legs"><option>2</option><option>3</option><option>4</option><option selected>5</option></select></label>
<label>Următoarele ore<input name="hours" type="number" min="1" max="168" value="48"></label>
<label>Prob. minimă / selecție<input name="min_prob" type="number" step="0.05" min="0.3" max="0.95" value="0.5"></label>
<button id="go" type="submit">Generează</button>
</form>
<div id="out"></div>
<div class="warn muted" id="disc"></div>
</main>
<script>
const out=document.getElementById('out'),btn=document.getElementById('go');
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e}
document.getElementById('f').addEventListener('submit',async ev=>{
  ev.preventDefault();btn.disabled=true;out.replaceChildren(el('p','muted','Se calculează...'));
  const q=new URLSearchParams(new FormData(ev.target));
  try{
    const r=await fetch('/suggest?'+q);const d=await r.json();
    if(!r.ok)throw new Error(d.detail||('HTTP '+r.status));
    out.replaceChildren();
    out.append(el('p','muted',d.events_analyzed+' meciuri analizate · '+d.generated_at+(d.quota&&d.quota.remaining?' · credite API rămase: '+d.quota.remaining:'')));
    d.notes.forEach(n=>out.append(el('p','muted',n)));
    d.combos.forEach((c,i)=>{
      const card=el('div','card'),head=el('div','head');
      head.append(el('span','', '#'+(i+1)+' · '+c.book_title),
        el('span','', 'cota '+c.odds.toFixed(2)+' · prob. ~'+Math.round(c.probability*100)+'% · EV '+(c.ev*100).toFixed(1)+'%'));
      card.append(head);
      c.legs.forEach(l=>{const row=el('div','leg'),left=el('div'),right=el('div');
        left.append(el('div','',l.match),el('small','',l.league+' · '+l.start));
        right.append(el('div','',l.pick+' @ '+l.odds.toFixed(2)),el('small','','prob. ~'+Math.round(l.fair_probability*100)+'%'));
        row.append(left,right);card.append(row)});
      out.append(card)});
    if(d.explanation){const c=el('div','card');c.append(el('div','head','Explicație'),el('p','',d.explanation));out.append(c)}
    document.getElementById('disc').textContent=d.disclaimer;
  }catch(e){out.replaceChildren(el('p','',String(e.message||e)))}
  finally{btn.disabled=false}
});
</script></body></html>"""


def create_app(
    settings: Settings | None = None,
    provider: OddsProvider | None = None,
    llm: LLM | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    provider = provider or OddsProvider(settings)
    llm = llm or LLM(settings)
    lock = threading.Lock()  # o singură actualizare de cote o dată: protejează creditele API
    app = FastAPI(title="Odds Agent", version=__version__, docs_url=None, redoc_url=None)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return PAGE

    @app.get("/suggest")
    def suggest_endpoint(
        target: float = Query(2.0, ge=1.2, le=10.0),
        max_legs: int = Query(5, ge=2, le=5),
        hours: int = Query(48, ge=1, le=168),
        min_prob: float = Query(0.5, ge=0.3, le=0.95),
        rank_by: str = Query("ev", pattern="^(ev|prob)$"),
        explain: bool = True,
    ) -> dict:
        try:
            with lock:
                return suggest(
                    settings,
                    provider,
                    llm,
                    target=target,
                    max_legs=max_legs,
                    hours=hours,
                    min_prob=min_prob,
                    rank_by=rank_by,
                    explain=explain,
                )
        except ProviderError as error:
            raise HTTPException(status_code=502, detail=str(error)) from None

    return app

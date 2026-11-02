# Odds Agent

Agent local (Python, Docker) care citește **cotele reale** ale mai multor case de pariuri și propune bilete cu **cota totală în jur de 2.0**, din **maximum 5 meciuri** (2 până la 5 selecții, la aceeași casă).

Nu plasează pariuri, nu se autentifică nicăieri și nu atinge bani. Generează doar sugestii.

## Ce poți aștepta, sincer

- Un bilet cu cota 2.0 înseamnă, matematic, o șansă de câștig de aproximativ **50%**, minus marja casei. Nu există un bilet „foarte sigur" la cota 2.0.
- Casele au o **marjă** (de obicei câteva procente per meci), iar la bilete combinate marja se compune. De aceea, pe termen lung, valoarea așteptată (EV) este de obicei **negativă**. Agentul o afișează ca să vezi singur.
- Agentul alege cele mai probabile selecții și cele mai bune combinații pe baza consensului caselor. **Nu are informații despre accidentări, formă sau motivație**, deci nu „știe" mai mult decât piața.
- Mai puține selecții înseamnă mai puține șanse ca un singur meci să strice biletul. La aceeași cotă totală, 2-3 selecții sunt de obicei mai robuste decât 5.
- Doar 18+. Joacă responsabil și doar sume pe care ți le permiți.

## Cum funcționează

1. Descarcă cotele 1X2 de la **The Odds API** (agregă multe case). Rezultatele sunt puse în cache pe disc, ca să economisești creditele gratuite.
2. Pentru fiecare meci scoate marja caselor și face media probabilităților (**consens**), folosind doar meciurile cu cel puțin `MIN_BOOKS` case.
3. Păstrează selecțiile cu probabilitate peste prag (implicit 50%).
4. Caută, **pentru fiecare casă în parte**, combinații de 2-5 meciuri diferite cu cota totală între `țintă - 0.05` și `țintă + 0.20`. Un bilet real se plasează la o singură casă, deci cotele nu se amestecă între case.
5. Le ordonează după EV (sau după probabilitate, cu `rank_by=prob`).
6. Opțional, un model LLM scrie o explicație scurtă. **Modelul nu alege și nu modifică nimic**: tot calculul este determinist și testat.

De ce nu „intră pe site-urile caselor": paginile lor au de obicei termeni care interzic accesul automat, detecție de roboți și restricții geografice. Un API de cote este mai stabil, mai rapid și respectă regulile furnizorului.

## Pornire rapidă (Windows, PowerShell)

Cerințe: Docker Desktop pornit.

```powershell
cd odds-agent
copy .env.example .env
notepad .env          # completează ODDS_API_KEY
docker compose up -d --build
```

Deschide **http://localhost:8000**. Pagina rulează doar pe calculatorul tău (portul e legat la `127.0.0.1`).

Alte moduri de folosire:

```powershell
# în terminal
docker compose run --rm agent python -m oddsagent suggest --target 2.0 --max-legs 4

# API (JSON)
curl "http://localhost:8000/suggest?target=2.0&max_legs=4&hours=48"

# chei de ligi disponibile
docker compose run --rm agent python -m oddsagent sports
```

Oprire: `docker compose down` (cache-ul din volum se păstrează).

## Costuri

| Componentă | Cost |
|---|---|
| Cote | Planul gratuit The Odds API, cu limită lunară de credite. Verifică limitele curente pe site. |
| LLM `none` (implicit) | 0, fără explicații text |
| LLM `ollama` | 0, rulează pe PC-ul tău |
| LLM `openai` | Gratuit cu cotă sau plătit, în funcție de furnizor |

Fiecare ligă din `ODDS_SPORTS` consumă aproximativ un credit la fiecare reîmprospătare. Cache-ul (`CACHE_TTL_SECONDS`, implicit o oră) ține consumul mic. Restrânge `ODDS_SPORTS` la ligile care te interesează.

## Alegerea modelului LLM

Se schimbă din `.env`, fără modificări de cod.

**Fără LLM (implicit):** `LLM_BACKEND=none`.

**Local, gratuit (Ollama):**

```powershell
# în .env: LLM_BACKEND=ollama
docker compose --profile local-llm up -d
docker compose exec ollama ollama pull llama3.2:3b
```

Modelul se descarcă o singură dată (câțiva GB). Fără placă video e mai lent, dar funcționează pentru explicații scurte.

**API compatibil OpenAI:** `LLM_BACKEND=openai`, apoi `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`. Exemple de adrese de bază (verifică modelele și cotele în documentația furnizorului): `https://api.openai.com/v1`, `https://api.groq.com/openai/v1`, `https://generativelanguage.googleapis.com/v1beta/openai/`.

## Parametri

| Parametru | Implicit | Sens |
|---|---|---|
| `target` | 2.0 | cota totală dorită |
| `max_legs` | 5 | număr maxim de meciuri (2-5) |
| `hours` | 48 | meciuri care încep în următoarele ore |
| `min_prob` | 0.5 | probabilitatea minimă a unei selecții |
| `rank_by` | `ev` | `ev` sau `prob` (cele mai probabile) |

Pentru biletele cele mai „realizabile" încearcă `rank_by=prob` și `max_legs=3`.

## Securitate

- Containerul rulează ca utilizator fără privilegii, cu sistem de fișiere read-only, fără capabilități Linux și cu limite de memorie și procese.
- Singurul loc scriibil este volumul `/data` (cache).
- Cheile API stau doar în `.env` (exclus din git și din imaginea Docker) și nu apar în erori sau în cache.
- Pagina web nu este expusă în rețeaua locală.

## Dezvoltare și teste

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt pytest
$env:PYTHONPATH = "src"
.venv\Scripts\python -m pytest -q tests
```

Testele nu folosesc rețeaua. Structura:

```
src/oddsagent/
  oddsmath.py   marjă, consens, căutarea combinațiilor
  provider.py   client The Odds API + cache
  llm.py        none / ollama / openai-compatibil
  service.py    orchestrare
  api.py        FastAPI + pagina web
  __main__.py   CLI (serve, suggest, sports)
```

## Idei de extindere

- Piețe suplimentare (sub/peste, handicap) și alte sporturi, prin `ODDS_SPORTS`.
- Date de formă și accidentări dintr-un API sportiv, ca să aibă ceva în plus față de piață.
- Istoric al sugestiilor și al rezultatelor, ca să verifici în timp dacă EV-ul estimat se confirmă.

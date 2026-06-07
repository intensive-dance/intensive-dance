# Candidate pipeline

The **loose backlog** of discovered providers — *before* they become a `seed`
in `providers.json` or get a GitHub issue. Keeps the issue tracker clean while still
making every discovery visible (incl. to parallel collaborators).

## How a candidate moves through the pipeline

| status | meaning | lives in |
|---|---|---|
| `scored` | discovered + reviewed, not yet acted on | **this file** |
| `seed` | confirmed buildable + in the build queue | `providers.json` (`status: seed`) |
| `building` | issue opened + self-assigned, scraper WIP | issue + `providers.json` |
| `live` | merged scraper, in the register | `providers.json` (`status: live`) |
| `parked` | real intensive, but no *current dated* edition yet — re-check later | this file |
| `deferred` | full-time / long-term *Ausbildung* only → IDR-9 (#12) | issue (`phase-2`) |
| `out-of-scope` | competition / recreational / adult-only | this file (skip) |

**Rule:** a new discovery starts here. We create a **US (issue) only when we
start building** (the claim, to avoid colliding with parallel work) **or when we defer**
(the IDR-9 stub). We promote to `seed` when it's a confirmed in-scope build target.

---

## 🔝 Build queue — immediately buildable (dated 2026, in-scope)

The recommended next builds — discovered, in scope, with a confirmed dated 2026 edition.

| Provider | Country · City | 2026 dates | URL |
|---|---|---|---|
| Stage Int. de Danse Charles Jude | FR · Marseille | 6–18 Jul | stagedansecj.com |
| Académie Int. de Danse de Biarritz | FR · Biarritz | 2–7 Aug | biarritz-academie-danse.com |
| Stage Int. de Danse d'Arcachon | FR · Arcachon | 6–18 Jul | stagedansearcachon.com |
| Académie Theilaïa (Nini Theilade) | FR · Lyon | 13–17 Jul | academie-ballet.fr |
| BalletStage Summer Intensive (Matvienko) | SI · Ljubljana | 13–25 Jul | balletstage.com |
| Prague Ballet Intensive (≠ IBMC Prague) | CZ · Prague | 10–22 Aug | pragueballetintensive.com |
| Académie Int. d'Été de Nice | FR · Nice | 27 Jul–1 Aug | academie-internationale-ete-nice.org |
| Revolve Dance Festival | RO · Bucharest | 10–23 Aug | revolvedance.ro |
| Ballet Workshops Bucharest | RO · Bucharest | 9–19 Jul | balletworkshops.com |
| Balletto di Roma — Summer School | IT · Rome | 6 Jul–5 Sep (blocks) | store.ballettodiroma.com |
| Nuovo Balletto Classico | IT · Reggio Emilia | 29 Jun–18 Jul | nuovoballettoclassico.it |
| EDCN — Conservatório Nacional | PT · Lisbon | 13–18 Jul | edcn.pt |
| ENDANSA'IT — Institut del Teatre | ES · Barcelona | 29 Jun–2 Jul | institutdelteatre.cat |
| RCPD "Mariemma" Summer (Magistra Danza) | ES · Madrid | 29 Jun–3 Jul | rcpdmariemma.com |
| Ballet Ireland Summer Intensive | IE · Dublin | 27–31 Jul + 4–8 Aug | balletireland.ie |
| ArtéBallét Advanced Summer | NL · Amsterdam | 27 Jul–8 Aug | (own URL TBD) |
| Cuban Ballet Program | BE · Antwerp | 10–15 Aug | cubanballetprogram.com |
| SADA Phoenix Summer | AT · Salzburg | 13 Jul–1 Aug | sada.dance |
| NDT Summer Intensive (contemp) | NL · The Hague | 27 Jul–8 Aug | ndt.nl |
| Rambert School Performance & Technique (contemp) | GB · London | 13–25 Jul | rambertschool.org.uk |
| Yorkshire Ballet Seminars | GB · Harrogate | 12 Jul–8 Aug | ybss.co.uk |
| Tivoli Balletskole Summercamp | DK · Copenhagen | 29 Jun–4 Jul | tivoliballetskole.dk |
| Professione Danza Pescara | IT · Pescara | 1–24 Jul | professionedanza.org |
| LETO BALETA (After Petipa) | BG · Kranevo | 26 Jul–8 Aug | afterpetipa.com |
| Eszena Danza — Intensivos | ES · Madrid | Jun–Aug blocks | eszena.es |
| Valencia Endanza | ES · Valencia | ~13–25 Jul | valenciaendanza.com |

## 📡 Monitor — recurring, 2026 dates not yet posted (`parked`/`scored`)
- Teatro dell'Opera di Roma — Stage Estivo (IT · Rome, Abbagnato) — 2026 page live, dates ~July TBA — operaroma.it
- PHP Ballet Intensive (CH, Béjart-principal founders) — dates need render/email — phpballetintensive.ch
- Accademia Bozzolini / Balletto di Toscana SI (IT · Florence) — 2025 ran 7–19 Jul; 2026 TBA
- Tallinn Summer Ballet (EE) · Ballet Summer Workshop Estonia (EE) · Balletto di Verona (IT) · Opus Ballet (IT · Florence) — annual, 2026 dates pending
- GB verify-before-build: Moorland Int'l Ballet · Ballet Boost · The Hammond · Ballet West — exist annually, no live 2026 dates found (don't assert)
- cordsdance — Intensive Ballet Workshops (PL · Wrocław, AST-Halle) — 5th ed., classical + contemporary; **20–25 Jun + 20–25 Jul 2026 announced on Instagram (@cordsdance)**, but the site's 2026 page isn't up yet (only 2023–25 exist) — cordsdance.com. Local studio, faculty unnamed. *(Instagram-sourced.)*
- Summer Intensive Gymnasium Essen-Werden (DE · Essen) — **already a `seed`** in providers.json; school-based summer intensive, faculty incl. Paula Archangelo-Cakir (ex-Aalto Ballett Theater Essen / dance medicine). *(Instagram-sourced @gymnasium_essen_werden_tanz; recorded here for tracking.)*

## ⏸️ Defer → IDR-9 (`deferred`) — full-time / long-term only, no short course
- School of the Hamburg Ballet (DE) · Ballettakademie der Wiener Staatsoper (AT) · Royal Swedish Ballet School (SE) · Greek National Opera Dance School (GR) · Teatro di San Carlo Ballet School (IT · Naples) · Ginasiano (PT) · Čiurlionis School (LT) · Floria Capsali (RO) · CPD Sevilla (ES)

## 🚫 Out of scope (`out-of-scope`)
- **Competitions:** Prix de Lausanne, YAGP, Varna IBC + its competition-linked summer academy, Dance World Cup.
  - ⚠️ **Scope decision needed:** *Prix de Lausanne **Summer Intensive*** (CH, 6–11 Jul 2026) is the training feeder, **not** the competition — could be in-scope. Currently treated as out-of-scope pending your call.
- **Adult-only:** Ballet Gothenburg Adult Ballet Retreat (SE) — high-calibre SAB/NYCB faculty, but adults only.
- **Recreational/local:** Leipziger Ballettschule · Iwanson (contemp) · Grand Art Ballet (HU) · Paris Marais Dance School (amateur) · CPD Valencia / Eszena lower tracks.

## ℹ️ Notes — overlaps with what we already have / scope
- **Joffrey Switzerland** (Geneva, 10–15 Aug 2026) and **Joffrey Japan** are programs of **Joffrey Ballet School** — should be captured by the existing `joffrey-ballet-school` scraper. Verify coverage rather than adding a new provider.
- **Russian Masters Ballet — Burgas** (BG, 27 Jul–17 Aug 2026) is a *location* of the existing `russian-masters-ballet` provider → add as an offering, not a new provider.
- **Dutch National Ballet Academy — Amsterdam International Summer School** (Senior 6–17 Jul, Junior 13–17 Jul 2026) is the summer course of our existing `dutch-national-ballet-academy` → confirm the scraper emits it.
- **ART of Madrid** (13–25 Jul) is already covered under `art-of-zurich` (one org, two locations).
- **BRB Summer Intensive (via GradPro)** (GB) — narrow entry (1st/2nd-yr vocational only); lower priority despite the BRB brand.
- **High-yield discovery indexes for future passes:** `danseclassique.info/stages/saisons/ete/` (FR étoile-led stages), `balletchannel.jp` / `ballet-search.com` (JP dated workshops).

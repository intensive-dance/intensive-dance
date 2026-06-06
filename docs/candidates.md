# Candidate pipeline (scored)

The **loose, scored backlog** of discovered providers — *before* they become a `seed`
in `providers.json` or get a GitHub issue. Keeps the issue tracker clean while still
making every discovery visible (incl. to parallel collaborators).

## How a candidate moves through the pipeline

| status | meaning | lives in |
|---|---|---|
| `scored` | discovered + tier-scored, not yet acted on | **this file** |
| `seed` | confirmed buildable + in the build queue | `providers.json` (`status: seed`) |
| `building` | issue opened + self-assigned, scraper WIP | issue + `providers.json` |
| `live` | merged scraper, in the register | `providers.json` (`status: live`) |
| `parked` | real intensive, but no *current dated* edition yet — re-check later | this file |
| `deferred` | full-time / long-term *Ausbildung* only → IDR-9 (#12) | issue (`phase-2`) |
| `out-of-scope` | competition / recreational / adult-only | this file (skip) |

**Rule:** a new discovery starts as `scored` here. We create a **US (issue) only when we
start building** (the claim, to avoid colliding with parallel work) **or when we defer**
(the IDR-9 stub). We promote to `seed` when it's a confirmed in-scope build target.

**Tier** = quick P-Score read (faculty/founder pedigree → S marquee · A significant ·
B regional · C local/recreational). Full 6-signal P-Score (see #46 / #91) is computed at
build time. **✅ = genuine dated 2026 edition confirmed (immediately buildable).**

---

## 🔝 Build queue — immediately buildable (`scored`, dated 2026, in-scope)

Ranked by tier then confidence. These are the recommended next builds.

| Tier | Provider | Country · City | 2026 dates | URL |
|---|---|---|---|---|
| **S** | Stage Int. de Danse Charles Jude | FR · Marseille | 6–18 Jul | stagedansecj.com |
| **S** | Académie Int. de Danse de Biarritz | FR · Biarritz | 2–7 Aug | biarritz-academie-danse.com |
| **S** | Stage Int. de Danse d'Arcachon | FR · Arcachon | 6–18 Jul | stagedansearcachon.com |
| **S** | Académie Theilaïa (Nini Theilade) | FR · Lyon | 13–17 Jul | academie-ballet.fr |
| **S** | BalletStage Summer Intensive (Matvienko) | SI · Ljubljana | 13–25 Jul | balletstage.com |
| **S/A** | Prague Ballet Intensive (≠ IBMC Prague) | CZ · Prague | 10–22 Aug | pragueballetintensive.com |
| **S/A** | Académie Int. d'Été de Nice | FR · Nice | 27 Jul–1 Aug | academie-internationale-ete-nice.org |
| **A/S** | Revolve Dance Festival | RO · Bucharest | 10–23 Aug | revolvedance.ro |
| **A** | Ballet Workshops Bucharest | RO · Bucharest | 9–19 Jul | balletworkshops.com |
| **A** | Balletto di Roma — Summer School | IT · Rome | 6 Jul–5 Sep (blocks) | store.ballettodiroma.com |
| **A** | Nuovo Balletto Classico | IT · Reggio Emilia | 29 Jun–18 Jul | nuovoballettoclassico.it |
| **A** | EDCN — Conservatório Nacional | PT · Lisbon | 13–18 Jul | edcn.pt |
| **A** | ENDANSA'IT — Institut del Teatre | ES · Barcelona | 29 Jun–2 Jul | institutdelteatre.cat |
| **A** | RCPD "Mariemma" Summer (Magistra Danza) | ES · Madrid | 29 Jun–3 Jul | rcpdmariemma.com |
| **A** | Ballet Ireland Summer Intensive | IE · Dublin | 27–31 Jul + 4–8 Aug | balletireland.ie |
| **A** | ArtéBallét Advanced Summer | NL · Amsterdam | 27 Jul–8 Aug | (own URL TBD) |
| **A** | Cuban Ballet Program | BE · Antwerp | 10–15 Aug | cubanballetprogram.com |
| **A** | SADA Phoenix Summer | AT · Salzburg | 13 Jul–1 Aug | sada.dance |
| **A** (contemp) | NDT Summer Intensive | NL · The Hague | 27 Jul–8 Aug | ndt.nl |
| **A** (contemp) | Rambert School Performance & Technique | GB · London | 13–25 Jul | rambertschool.org.uk |
| **A/B** | Yorkshire Ballet Seminars | GB · Harrogate | 12 Jul–8 Aug | ybss.co.uk |
| **A/B** | Tivoli Balletskole Summercamp | DK · Copenhagen | 29 Jun–4 Jul | tivoliballetskole.dk |
| **B** | Professione Danza Pescara | IT · Pescara | 1–24 Jul | professionedanza.org |
| **B** | LETO BALETA (After Petipa) | BG · Kranevo | 26 Jul–8 Aug | afterpetipa.com |
| **B** | Eszena Danza — Intensivos | ES · Madrid | Jun–Aug blocks | eszena.es |
| **B** | Valencia Endanza | ES · Valencia | ~13–25 Jul | valenciaendanza.com |

## 📡 Monitor — recurring, 2026 dates not yet posted (`parked`/`scored`)
- **S** Teatro dell'Opera di Roma — Stage Estivo (IT · Rome, Abbagnato) — 2026 page live, dates ~July TBA — operaroma.it
- **A** PHP Ballet Intensive (CH, Béjart-principal founders) — dates need render/email — phpballetintensive.ch
- **A/B** Accademia Bozzolini / Balletto di Toscana SI (IT · Florence) — 2025 ran 7–19 Jul; 2026 TBA
- **B** Tallinn Summer Ballet (EE) · Ballet Summer Workshop Estonia (EE) · Balletto di Verona (IT) · Opus Ballet (IT · Florence) — annual, 2026 dates pending
- GB verify-before-build: Moorland Int'l Ballet · Ballet Boost · The Hammond · Ballet West — exist annually, no live 2026 dates found (don't assert)

## ⏸️ Defer → IDR-9 (`deferred`) — full-time / long-term only, no short course
- **S** School of the Hamburg Ballet (DE) · **A** Ballettakademie der Wiener Staatsoper (AT) · Royal Swedish Ballet School (SE) · Greek National Opera Dance School (GR) · Teatro di San Carlo Ballet School (IT · Naples) · Ginasiano (PT) · Čiurlionis School (LT) · Floria Capsali (RO) · CPD Sevilla (ES)

## 🚫 Out of scope (`out-of-scope`)
- **Competitions:** Prix de Lausanne, YAGP, Varna IBC + its competition-linked summer academy, Dance World Cup.
  - ⚠️ **Scope decision needed:** *Prix de Lausanne **Summer Intensive*** (CH, 6–11 Jul 2026) is the training feeder, **not** the competition — could be in-scope. Currently treated as out-of-scope pending your call.
- **Adult-only:** Ballet Gothenburg Adult Ballet Retreat (SE) — S-tier SAB/NYCB faculty, but adults only.
- **Recreational/local:** Leipziger Ballettschule · Iwanson (contemp) · Grand Art Ballet (HU) · Paris Marais Dance School (amateur) · CPD Valencia / Eszena lower tracks.

## ℹ️ Notes — overlaps with what we already have / scope
- **Joffrey Switzerland** (Geneva, 10–15 Aug 2026) and **Joffrey Japan** are programs of **Joffrey Ballet School** — should be captured by the existing `joffrey-ballet-school` scraper. Verify coverage rather than adding a new provider.
- **Russian Masters Ballet — Burgas** (BG, 27 Jul–17 Aug 2026) is a *location* of the existing `russian-masters-ballet` provider → add as an offering, not a new provider.
- **Dutch National Ballet Academy — Amsterdam International Summer School** (Senior 6–17 Jul, Junior 13–17 Jul 2026) is the summer course of our existing `dutch-national-ballet-academy` → confirm the scraper emits it.
- **ART of Madrid** (13–25 Jul) is already covered under `art-of-zurich` (one org, two locations).
- **BRB Summer Intensive (via GradPro)** (GB) — narrow entry (1st/2nd-yr vocational only); lower priority despite the BRB brand.
- **High-yield discovery indexes for future passes:** `danseclassique.info/stages/saisons/ete/` (FR étoile-led stages), `balletchannel.jp` / `ballet-search.com` (JP dated workshops).

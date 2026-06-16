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

## 🔝 Build queue

**The live buildable list is [`buildable.md`](./buildable.md)** — generated from `providers.json` (drift-checked in CI), grouped by country, with the claim convention. We no longer hand-maintain a build-queue *table* here (it drifted as providers went live); this file keeps only **build hints** not stored in the register.

**Build hints (source shape / audition):**
- *American Midwest Ballet* (Omaha) — WordPress (`/wp-content/` → try `/wp-json/`); ages 11–25 (+ Junior 10–13); online audition = teacher recommendation + 1st-arabesque & tendu-à-la-seconde photos (defined-poses).
- *Master Ballet Academy* (Scottsdale, Vaganova) — Wix (watch zero-width spaces); 6-week, min 3 wks; audition = headshot + 1st-arabesque photo (video/Zoom/in-person).
- *Art in Motion Munich* — Wix static; 3–15 Aug 2026 (deadline 15 Jul). *Tanzquartier Köln* — WordPress (`/wp-json/`); 31 Jul–4 Aug + 24–28 Aug 2026.

## 📡 Monitor — recurring, 2026 dates not yet posted (`parked`/`scored`)
- Teatro dell'Opera di Roma — Stage Estivo (IT · Rome, Abbagnato) — 2026 page live, dates ~July TBA — operaroma.it
- PHP Ballet Intensive (CH, Béjart-principal founders) — dates need render/email — phpballetintensive.ch
- Accademia Bozzolini / Balletto di Toscana SI (IT · Florence) — 2025 ran 7–19 Jul; 2026 TBA
- Tallinn Summer Ballet (EE) · Ballet Summer Workshop Estonia (EE) · Balletto di Verona (IT) · Opus Ballet (IT · Florence) — annual, 2026 dates pending
- GB verify-before-build: Moorland Int'l Ballet · Ballet Boost · The Hammond · Ballet West — exist annually, no live 2026 dates found (don't assert)
- cordsdance — Intensive Ballet Workshops (PL · Wrocław, AST-Halle) — 5th ed., classical + contemporary; **20–25 Jun + 20–25 Jul 2026 announced on Instagram (@cordsdance)**, but the site's 2026 page isn't up yet (only 2023–25 exist) — cordsdance.com. Local studio, faculty unnamed. *(Instagram-sourced.)*
- **Umbria Ballet — PBS Summer Studio** (IT · Bastia Umbra, prov. Perugia) — **already a `seed`** in providers.json; Centro Professionale di Danza founded 2005 by dir. Marina Tofi, runs a recurring week-long **P.B.S. Summer Studio** intensive with dir. Luca Masala + faculty from the **Académie Princesse Grace de Monte-Carlo** (classical + contemporary, men's/women's technique, repertoire, music). Last concretely-dated edition found = 2020 (29 Jun–4 Jul); **2026 dates not yet verified** (site bot-gated). Source = **WordPress/WooCommerce** (`/prodotto/p-b-s-summer-studio/`, `/negozio/`, `?lang=en` → likely WPML/Polylang) — direct fetch **403s, proxy needed**. — umbriaballet.com
- Summer Intensive Gymnasium Essen-Werden (DE · Essen) — **already a `seed`** in providers.json; school-based summer intensive, faculty incl. Paula Archangelo-Cakir (ex-Aalto Ballett Theater Essen / dance medicine). *(Instagram-sourced @gymnasium_essen_werden_tanz; recorded here for tracking.)*

## ⏸️ Defer → IDR-9 (`deferred`) — full-time / long-term only, no short course
- School of the Hamburg Ballet (DE) · Ballettakademie der Wiener Staatsoper (AT) · Royal Swedish Ballet School (SE) · Greek National Opera Dance School (GR) · Teatro di San Carlo Ballet School (IT · Naples) · Ginasiano (PT) · Čiurlionis School (LT) · Floria Capsali (RO) · CPD Sevilla (ES)

## 🚫 Out of scope (`out-of-scope`)
- **Competitions:** Prix de Lausanne, YAGP, Varna IBC + its competition-linked summer academy, Dance World Cup.
  - ⚠️ **Scope decision needed:** *Prix de Lausanne **Summer Intensive*** (CH, 6–11 Jul 2026) is the training feeder, **not** the competition — could be in-scope. Currently treated as out-of-scope pending your call.
- **Adult-only:** Ballet Gothenburg Adult Ballet Retreat (SE) — high-calibre SAB/NYCB faculty, but adults only.
- **Recreational/local:** Leipziger Ballettschule · Iwanson (contemp) · Grand Art Ballet (HU) · Paris Marais Dance School (amateur) · CPD Valencia / Eszena lower tracks.

## 🇩🇪 DE Top-10-Städte-Sweep (2026-06-09)

Multi-agent Phase-1 sweep of Germany's ten largest cities (Berlin · Hamburg · Munich ·
Cologne · Frankfurt · Stuttgart · Düsseldorf · Leipzig · Dortmund · Essen). ~80 providers
triaged; **6 promoted to `seed`** in `providers.json`, the rest recorded below. No tiers/scores
(those live privately).

**→ promoted to `seed`:**
- **Art in Motion Munich** (Munich) — annual 2-wk summer intensive, **3–15 Aug 2026** (deadline 15 Jul), ages 10+, classical + pointe + repertoire + modern; faculty HMTM-affiliated (Gabriela Nicolescu) at Heinz-Bosl-Stiftung studios — artinmotionmunich.com *(Wix/static HTML)*
- **Tanzquartier Köln** (Cologne) — Ballett + Contemporary Intensiv-Workshop, **two 2026 editions: 31 Jul–4 Aug & 24–28 Aug**, ages 10+/14+, Förderstufe pre-pro track — tanzquartier.koeln *(**WordPress** — try `/wp-json/`)*
- **Hamburger Ballett-Tanztage / GinaWorkshops** (Hamburg) — recurring weekend ballet intensive (3 eds since 2023), company-calibre faculty (Bouchet, Riabko, Azzoni, Urban), ages ~16+; 4th ed TBA — ginaworkshops.com *(**WordPress**)*
- **Staatsballett Berlin — Feriencamp** (Berlin) — recurring 5-day camp, ages 12–16 (5-yr prerequisite), state-company education arm ("Tanz ist KLASSE!"); Oct 2026 confirmed, summer TBA — staatsballett-berlin.de
- **Benedict Manniegel Ballet School** (Munich) — Vaganova school, dir. ex-Hamburg Ballet/Het Nationale Ballet prima; Easter workshop 2026 confirmed, summer TBA — benedictmanniegel.de
- **Ballett- und Tanzschule Anastasia** (Frankfurt am Main) — recurring annual "Sommer Intensive" (week 1 of summer holidays), Vaganova pre-pro track; 2026 dates TBA *(verify post-2022 continuity)* — ballett-und-tanzschule-anastasia.com *(**WordPress**)*
- **DBfT — Sommerakademie Junior** (Dortmund) — intensive training week by the Deutscher Berufsverband für Tanzpädagogik in cooperation with the Internationale Sommerakademie des Ballett Dortmund; ages 13–15, classical, two levels, summer holidays (2026 edition confirmed), at the Opernhaus Dortmund / Ballettzentrum Westfalen — dbft.de. *Distinct from the separate `ballett-dortmund` seed (the company's own Int. Sommerakademie).* *(User-requested seed 2026-06-11.)*

**`scored` — monitor / verify before promoting:**
- **ICZ Leipzig — Sommer-Akademie "Uwe Scholz"** (Leipzig) — annual 1-wk ballet intensive open to European students, dir. Montserrat León, on the Baumwollspinnerei campus; **recency uncertain** (nav says 6th ed, archive gaps post-2016) — icz-leipzig.de
- **Dance Hub Munich** (Munich) — youth summer week **31 Aug–4 Sep 2026**, ballet-centric school but age 6+/mixed-genre — confirm pre-pro depth — dancehubmunich.de
- **Sommer Tanz Camp — Intensive Ballet Days Berlin** (Berlin/Tempelhof) — recurring 4-day classical, ages 14+ intermediate–advanced; summer TBA, hosted at an urban-dance venue — sommertanzcamp.de
- **Tanzhaus1141** (Cologne-Weiden) — Bezirksregierung-Köln career-prep accredited, ballet-focused; no dated 2026 intensive published yet — tanzhaus1141.de
- **Star Ballet Mainz/Wiesbaden** (Rhein-Main) — pre-pro school w/ stated masterclass activity, but no dated open-enrollment intensive page — ballettschule-mainz.de

**`parked` — real school, no current public dated intensive:** Marameo Berlin · Lola Rogge Sommertanztage (Hamburg) · Ballettakademie Kashcheeva (Munich) · Ballettschule International Bonn · laDanse Niederkassel (Düsseldorf) · Colette van Saarloos (Neuss) · Schule des Balletts Stuttgart · Ballettschule Étoile (Leipzig) · Ballettakademie am Opernhaus Halle · Grand Jeté Dortmund.

**`deferred` → IDR-9 (full-time / Ausbildung only):** Int'l Dance Academy Berlin · CDSH Hamburg · Ballett-Akademie HMTM / Heinz-Bosl-Stiftung (Munich) · HfMT Köln · Dr. Hoch's Konservatorium + HfMDK Frankfurt + DAS Studio + Balzer + Akademie f. Ballett u. Tanz (Frankfurt) · Professional Dance Academy (Stuttgart) · Pergel-Ernst (Düsseldorf) · Ballettschule der Oper Leipzig · Folkwang Universität (Essen).

**`out-of-scope`:** DanceWorld Stuttgart (ballet **competition** component) · Stuttgarter Ballett JUNG+ (contemporary creative-movement outreach) · Hessisches Staatsballett Ballettworkshop (single 90-min session) · Traumtänzer Dortmund (all-levels + crafts) · Aalto Ballett open classes (single session) · numerous recreational/term-only schools.

## 🇦🇹 Austria / Vienna (2026-06-12)

Phase-1 sweep of Austria — Vienna + Graz · Salzburg · Linz · Innsbruck · St. Pölten — by
provider **and** program-type ("Sommerintensiv/Sommerakademie Ballett"), incl.
Verbände/Konservatorien/Privatuniversitäten. **2 promoted to `seed`**; rest recorded below.

**→ promoted to `seed`:**
- **Europaballett St. Pölten — Danceflash** (St. Pölten) — the dated **Sommerworkshop** of the
  state-funded **Europaballett Konservatorium** (Land NÖ); **4–11 Jul 2026** (8 days), ages 7–26
  (split 5–12 / 13–26), classical ballet + **pointe** + repertoire + pas de deux, faculty incl.
  former opera-house principals, closing gala at the Konservatorium (Oriongasse 4). Genuine
  pre-pro-leaning student intensive. — en.europaballett.at/ausbildung/danceflash (also
  danceflash.eu) *(site 403s a datacenter fetch → Phase-2 likely needs the proxy)*
- **Ballettratten — Sommerintensivkurs** (Vienna) — youth ballet intensive at **Ballettinstitut
  Döbling** (1190 Wien, Billrothstr. 16), ages **10–18**, grouped by age/level; **two 2026
  editions: 6–10 Jul & 31 Aug–4 Sep**; classical + **Spitzentechnik (pointe)** + variations +
  performance prep. (A separate 4–12 "Sommerballett" kids course and an adult intensive also run —
  build only the 10–18 student edition.) — ballettratten.com *(Joomla — `/neu/index.php/...`)*

**Already tracked elsewhere (do not re-seed):**
- **SADA Phoenix — Summer Dance Intensive** (Salzburg, Salzburg Academy for Dance Arts) — company-
  style 3-wk (13 Jul–1 Aug 2026) / 2-wk (20 Jul–1 Aug) residency, ages 13+ (≥3 yrs training),
  classical (Vaganova/Cuban) + contemporary + repertoire (Paquita, Breuer's Bolero), two public
  performances at Theatre Odeïon. **In scope, but already in the pipeline per the discovery brief** —
  recorded here only to avoid a duplicate seed. — sada.dance/programme/phoenix

**`scored` — real dated ballet course but recreational/amateur-leaning (verify pre-pro depth before promoting):**
- **Internationale Sommerakademie für Theater Graz (somak.at)** (Graz) — Verein-run summer academy,
  9–28 Aug 2026, 40+ workshops across acting/dance/singing; has **Ballett Basic** (Vaganova, "normal
  everyday fitness sufficient") **and Ballett Fortgeschrittene** (advanced). All-ages amateur framing
  (participants 6–80) — the *advanced* ballet track is the only possibly-in-scope piece; treated as
  out-of-scope for now (recreational/adult-education). — somak.at/ballett/
- **ballettferien.at — Oster-/Sommerkurse** (AT, location unconfirmed) — ballet-holiday format for
  "amateurs of all ages, training students and professionals"; classical/pointe/repertoire/character/
  musical, 1–6 h/day. No dated 2026 edition or clear city found; amateur-of-all-ages framing → verify
  a real pre-pro student edition before seeding. — ballettferien.at

**`parked` — school exists, no current public *dated pre-pro* intensive found:**
- **Ballett Graz — Mariya Mizinskaya** (Graz) — runs "Sommer Intensivkurse" but short daily sessions
  (1–1¼ h over 3 days), ages 5–7 / 8+, beginners+advanced incl. Ballettgymnastik/PBT → recreational
  children's school. — ballett-graz.at
- **Erste Linzer Ballettschule** (Linz) — recreational school, ages 4–60+; no dated 2026 summer
  intensive published. — ballettschule-linz.at
- **SIBA Ballettschule Salzburg** (Salzburg) — hobby + aspiring-pro, all ages; no dated summer
  intensive found. — sibaballettschule.at
- **Tanzacademy Innsbruck** (Innsbruck) — summer **camps** ages 5–14 ("latest styles & trends"),
  3 h/day, recreational multi-style — not a pre-pro ballet intensive. — tanzacademy.at/sommerkurse

**`deferred` → IDR-9 (full-time / degree only, no public short-term intensive):**
- **MUK – Musik und Kunst Privatuniversität der Stadt Wien** (ex-Konservatorium Wien) — BA Classical &
  Contemporary Dance + Pre-College Dance (14+, autumn start); its only "Sommerakademie" is the Vienna
  Philharmonic *music* academy, not dance. — muk.ac.at
- **Ballettakademie der Wiener Staatsoper** (Vienna) — already on the IDR-9 list (full-time
  vocational). — wiener-staatsoper.at
- **SADA — Dance Vision** (Salzburg) — full-year vocational program (the school's degree track;
  distinct from the in-scope Phoenix summer intensive above). — sada.dance

**`out-of-scope`:**
- **Competitions → icebox #80:** VIBE – Vienna International Ballet Experience (Gregor Hatala;
  30 Mar–1 Apr 2026, a dance challenge incl. dancers with disabilities) · Ballet Grand Prix Vienna.
- **Recreational / adult / term-only:** Tanzausbildung Wien "Sommerakademie" (12–18 Jul 2026, "no
  dance experience required", contemporary, berufsbegleitend) · Tanzstudio Manhardt (künstlerischer
  Tanz) · Performing Center Austria · DanceWorld Wien · DANCEBASE-Vienna · dancefit-studio · beat1060 ·
  Wiener VHS · USI Wien · Foundations Dance Collective Graz — recreational/hobby/adult studios with no
  dated pre-pro student intensive.

## ℹ️ Notes — overlaps with what we already have / scope
- **Joffrey Switzerland** (Geneva, 10–15 Aug 2026) and **Joffrey Japan** are programs of **Joffrey Ballet School** — should be captured by the existing `joffrey-ballet-school` scraper. Verify coverage rather than adding a new provider.
- **Russian Masters Ballet — Burgas** (BG, 27 Jul–17 Aug 2026) is a *location* of the existing `russian-masters-ballet` provider → add as an offering, not a new provider.
- **Dutch National Ballet Academy — Amsterdam International Summer School** (Senior 6–17 Jul, Junior 13–17 Jul 2026) is the summer course of our existing `dutch-national-ballet-academy` → confirm the scraper emits it.
- **ART of Madrid** (13–25 Jul) is already covered under `art-of-zurich` (one org, two locations).
- **BRB Summer Intensive (via GradPro)** (GB) — narrow entry (1st/2nd-yr vocational only); lower priority despite the BRB brand.
- **High-yield discovery indexes for future passes:** `danseclassique.info/stages/saisons/ete/` (FR étoile-led stages), `balletchannel.jp` / `ballet-search.com` (JP dated workshops).

## 🌍 Vienna region — broader + cross-border (live parallel sweep 2026-06-12)

Live 4-agent Phase-1 sweep: Vienna + its surroundings + the important cities near Vienna across the border (Bratislava SK · Brno CZ · Győr HU). Searched by provider **and** program-type, incl. Vereine/Konservatorien/festivals. **5 promoted to `seed`**; rest below.

**→ promoted to `seed`:**
- **Vienna Ballet Academy (Wiener Ballettakademie)** (Vienna, AT) — private academy with a recurring **Summer Intensive** (classical + contemporary + jazz + character); `/SummerIntensive` page confirmed, **2026 dates not extractable (JS/SPA)** → Phase-2 needs a render. — wienerballettakademie.com
- **abcDance — Academy of Ballet & Contemporary Dance** (Wiener Neustadt, AT — Vienna belt) — ballet + contemporary academy, dated **Sommer-Tanzcamps/-workshops 2026** (deadline 4 Jul; exact week dates live in schedule images) — abcdance.at
- **Staromestské baletné štúdio — Letná škola tanca** (Bratislava, SK · ~60 km) — Old-Town cultural-centre ballet studio; youth 12–18 **17–21 Aug 2026** (prior experience required), ballet + contemporary + variations; companion 8–11 edition 6–10 Jul — staromestskecentrakultury.sk
- **Baletní škola Pirueta — Letní baletní soustředění** (Brno, CZ · ~130 km) — 26th annual **residential** classical-ballet course, **27 Jul–2 Aug 2026**, ages 6–17, open to outside students — pirueta.cz
- **Győri Balett — Dance Intensive** (Győr, HU · ~120 km) — public open-enrollment ballet + contemporary workshop by the **Győr Ballet company** within the Hungarian Dance Festival (festival **17–21 Jun 2026**; 2025 ran 18–22 Jun); 2026 page not yet published. — gyoribalett.hu

**`scored` — dated public ballet course but recreational/kids-camp-leaning (verify depth first):**
- **TUTU Škola baletu — Detský letný tábor** (Bratislava, SK) — ex-SND-soloist studio; **27–31 Jul & 3–7 Aug 2026**, ~2 h ballet/day + performance, ages 5–12, €220 — skolabaletu.sk *(kids day-camp)*
- **Baletní škola Baláž — Top Ba-letní tábor** (Brno, CZ) — classical-ballet day-camp, **13–17 Jul & 3–7 Aug 2026**, ages 4–17 — balet-balaz.cz
- **Baletná škola Pointe — letné workshopy 2026** (Bratislava, SK) — pointe/advanced-leaning; **2026 registration open**, dates behind a form → Phase-2 probe — baletnaskolapointe.sk
- **ImPulsTanz – Vienna Int. Dance Festival** (Vienna, AT) — Europe's largest dance festival, **9 Jul–9 Aug 2026**, has a Ballet department + youth strand, but à-la-carte per-class booking (not a fixed cohort) — impulstanz.com
- *(Graz "Internationale Sommerakademie für Theater — Ballett" already evaluated in the Austria section above as recreational/adult-education — not re-promoted.)*

**`parked` / monitor — recurring, no current dated edition:** Tanzstudio Margit Manhardt (Vienna) · DanceFit Kids Ballet (Vienna, 17–21 Aug, ages 6–9) · RAUM für TANZ / Eva-Maria Kraft (Vienna, contemp.-ballet, 2026 TBA) · Baletné štúdio Terpsichoré & SIMART (Bratislava, dates TBA) · Konservatorij Maribor poletna baletna šola (SI, students-only) · Balet Filiánek (Brno, mostly own competition groups).

**`deferred` → IDR-9 (full-time / no public short course):** Tanečné konzervatórium Evy Jaczovej (Bratislava) · I. V. Psota Ballet School / Národní divadlo Brno · Slovak National Theatre Ballet (SND) · Académie de Danse Vienne (PDF-gated summer workshop — verify) · SoAk Tanz (sommerakademie.wien — genre conflict: one agent found no ballet → verify before any seed).

**`out-of-scope`:** Sopron Balett (HU, performing company only) · Szombathely schools (recreational) · adult/recreational summer courses (Pirueta adults · Vanda Skopalová Brno · Grand Art Ballet Budapest adult/teen · innstanz & Tanzacademy Innsbruck thin 1-class/day) · Ljubljana/Kamnik SI (far from the ring) · an Instagram-only "summer ballet academy" near Bratislava (unverifiable — not seeded).

## 🇷🇴 Romania (2026-06-13)

Phase-1 sweep of Romania — focus Bucharest + Cluj-Napoca · Timișoara · Iași — by provider
**and** program-type ("curs intensiv / școală de vară de balet", "masterclass / stagiu / tabără de
balet"), incl. asociații/fundații/academies and the National Operas' ballet arms. **2 promoted to
`seed`**; rest recorded below. Already `live` (untouched): **Revolve Dance Festival** (Bucharest —
2026 Summer Intensive confirmed **10–23 Aug 2026**, ages 9–20+, two weeks €700/€800, ≥6 h/day,
ballet + repertoire + pas de deux + neo-classic/contemporary, Stars Gala at the Bucharest National
Opera) and **Ballet Workshops Bucharest (Casa de Balet)** — both verified still current, not re-added.

**→ promoted to `seed`:**
- **La Sylphide Academic Ballet School** (Bucharest) — Vaganova school; via a 2017 protocol the first
  RO ballet school granting a state-recognised diploma. Runs a recurring, public **Summer School**
  (`/scoala-de-vara`) + **Workshops** with international guest teachers/choreographers/repetitors,
  open beyond its own pupils — the "full-time school also sells a public short course" case (build the
  summer school, not the year-round track). Prior editions found (2020, 2023, 2024 — reg. deadline
  25.06.2024); **2026 dates not yet posted** → Phase-2 to confirm. Site 403s a datacenter fetch
  (proxy likely). — baletcopii.com
- **Ballet Studio Felicia Șerbănescu** (Cluj-Napoca / Mărișel) — studio of ex-soloist *Maestra
  Pedagog Felicia Șerbănescu*; runs dated **residential masterclasses** in the Apuseni Mountains
  (Mărișel) — **classical + neoclassical + contemporary**, ages 13–18, small group (~10), group +
  individual work, competition prep, closing recital. Recurring (a summer ~16–26 Jul edition and a
  short autumn 4–6 Oct masterclass found); **2026 dates need confirmation** → Phase-2. Site 403s a
  datacenter fetch (proxy likely). — balletstudiofeliciaserbanescu.ro

**`scored` / `parked` — real dated/recurring ballet course but verify pre-pro depth or current dated edition before promoting:**
- **Academia de Balet Rapsodia** (Bucharest, Sala Rapsodia) — newly opened (May 2025) academy;
  states intensive preparation for adolescents aiming at a pro classical-dance career, with guest
  workshops by renowned RO/international figures. No **dated public summer edition** found yet (year-
  round, very new) → monitor. — academiadebalet.ro
- **Ballet Art** (Bucharest, dir. Iolanda Petrescu; Bolshoi-technique) — runs "Cursuri intensive de
  vară" but as a **rolling July 1–Aug 29 summer-class window** (classical + character + pilates +
  stretching), not a fixed dated cohort; sends pupils to *external* Bolshoi summer intensives abroad.
  Verify a fixed-week student intensive edition before seeding. — balet.ro
- **Bucharest City Ballet** (Bucharest) — pro company + affiliated school with an "international
  excellence" education programme; year-round courses/tariffs published but **no dated public summer
  intensive** surfaced (site 403s a datacenter fetch). Monitor. — bucharestcityballet.com
- **Azur Dance Studio — Tabără de vară** (Galați) — summer camp with ~4 h/day intensive ballet +
  technique/stretching/repertoire/stage work and visiting Bucharest/Opera teachers, but ages **6–16
  beginner–intermediate** (recreational kids-camp framing) and **outside the focus cities**; verify
  pre-pro depth + a 2026 edition before any seed. — azurdancestudio.ro

**`parked` — school exists, no current public dated pre-pro intensive found:** Black Swan Ballet
School (Timișoara — ballet + contemporary school, no dated summer intensive published) · Svetlana
Școală de balet academic (Bucharest) · Bucharest National Opera / Opera Iași / Opera Timișoara ballet
arms (company training, no public open-enrollment student intensive surfaced) · Dance Studio Cluj
(recreational) · Asociația Culturală Arlechin Botoșani (recreational school, ages 4–18).

**`out-of-scope` / already covered:**
- **Casa de Balet** (casadebalet.ro, Calea Dorobanți) — its "Școală de vară" is a **rolling 1 Jul–31
  Aug drop-in summer-class window**, not a dated cohort; and the Casa de Balet brand's dated student
  intensive (ages 9–18 in 9–11/12–14/15+ groups) is **already `live`** as `ballet-workshops-bucharest`
  → not re-added.
- **Recreational / kids-camp:** Stop and Dance · Centrul Cultural Reduta (Brașov, curs) · generic
  Bucharest summer-school listings (GOKID etc.).
- **`deferred` → IDR-9 (full-time / no public short course):** Liceul de Coregrafie *Floria Capsali*
  (Bucharest, vocational choreography high school — already on the IDR-9 list) · UNATC (degree).

## 🇨🇿 Czechia / Slovakia (2026-06-12)

Phase-1 sweep of CZ + SK, focus **Prague · Brno** (CZ) + **Bratislava** (SK), by provider
**and** program-type (`letní baletní/intenzivní kurz` CZ, `letný baletný kurz` SK), incl.
academies/conservatories/studios. Brno + Bratislava were largely covered by the prior
*Vienna region — cross-border* sweep above (Pirueta-Brno + Staromestské-Bratislava already
`seed`; TUTU / Baletná škola Pointe / Baláž `scored`; Terpsichoré / Filiánek `parked`; the
Brno/Bratislava conservatories `deferred`) — **do not re-seed those**. Net-new this pass = **3
Prague `seed`s**. Already `live` (do not touch): Prague Ballet Intensive · International Ballet
Masterclasses Prague · Jiří Bubeníček Ballet Masterclasses.

**→ promoted to `seed`:**
- **Prague Ballet Workshop — Classical Ballet Summer Workshop** (Prague, CZ) — recurring
  classical-ballet workshop in a central-Prague studio for **students of ballet schools /
  conservatories aged 13–21** (also runs an Easter edition). Distinct org from the live *Prague
  Ballet Intensive* (different domain). Classical (technique + repertoire); pre-pro-leaning. Home
  `<title>` still reads "…Easter Workshop 2025"; a **dated 2026 summer edition is not yet
  confirmed** (recurring annual) — verify dates in Phase-2 (don't assert). — pragueballetworkshop.com
  *(site 403s a datacenter fetch → Phase-2 likely needs the proxy; Wix-style multi-page site)*
- **Baletní akademie Adély Pollertové — letní soustředění** (Prague, CZ) — ballet school led by
  **Adéla Pollertová** (former first soloist, National Theatre Ballet Prague). Runs a dated summer
  intensive (`letní soustředění`) for older children, **17–21 Aug 2026**, classical. The school
  also teaches all-ages/recreational classes, so Phase-2 must scope to the dated student
  *soustředění*, not the term-time/adult offering. — baletniakademie.cz
- **First International Ballet School in Prague — Summer Camp** (Prague, CZ) — pre-pro classical
  school (English-medium; Creative Movement → Classical Ballet I–IV, ages 4–20, competition prep)
  that **also runs a public Summer Camp** (dedicated `/workshop/summer-camp/` page) — the
  "full-time school can still sell a public short course" case (verify-before-deferring). **2026
  camp dates / pre-pro depth not yet confirmed** — Phase-2 to verify it's a student intensive (not
  a young-children recreational camp) before building. — balletschoolprague.com

**`scored` / already-tracked — do not re-seed (see Vienna cross-border sweep above):**
- **Baletní akademie / DancePerfect / studio adult courses (Prague)** — `baletniakademie.cz` also
  sells adult ballet; `danceperfect.cz` summer Open-Class seminars are recreational multi-style →
  out of scope (the in-scope piece is the Pollertová youth *soustředění*, seeded above).
- **Baletná škola Pointe (Bratislava)** · **TUTU (Bratislava)** · **Baláž (Brno)** — already
  `scored`/kids-camp in the Vienna sweep; unchanged.

**`deferred` → IDR-9 (full-time / no public short course):** Taneční konzervatoř hl. m. Prahy ·
Taneční centrum Praha – konzervatoř · Duncan Centre konzervatoř (Prague, contemporary, full-time) ·
(Brno/Bratislava conservatories already listed in the Vienna sweep above).

**`out-of-scope`:** Košice recreational kids day-camps (Tanečné štúdio Hviezdička 6–10 Jul ages
5–12 · OUTBREAK summer camp ages 5+ · City Dance / NEXUM children's ballet) · La Tropical Prague
(adult-only intensive) · Pirueta adult residential course (Jul/Aug, adults) · SND "Soboty v divadle"
single-session TUTU taster workshops · BalletStage Summer Intensive (Ljubljana, SI — outside CZ/SK
scope, tracked in the SI/icebox notes).

# Job Search Aggregator

A small local web app that searches many job boards at once for the keywords you type, ranks the results by how well they match **both the job title and the job description**, and gives you the **link to each posting**. It also exports an **Excel application tracker** so you can keep track of where you are with each job.

It was built for a Philippines-based job seeker, so it covers:

- **Remote jobs** from employers outside the Philippines (filtered to those open to Philippines-based applicants, with no citizenship / work-authorization requirement)
- **Philippines-based jobs**, filterable by city (Manila, Makati, Taguig, Quezon City, Pasig, Cebu, Davao, Cagayan de Oro, Iloilo, Baguio, Clark, Bacolod)

Python standard library only for the server, plus `openpyxl` for the Excel export.

---

## Features

| Feature | Details |
|---|---|
| Keyword search | Type any role, e.g. `project manager`, `software project manager`, `technical delivery lead`. |
| Related roles | Your keywords are expanded to related roles (~100 management and leadership titles, plus engineering, product, design, support, data, marketing, sales, HR, QA, DevOps, writing, VA families). Searching "project manager" also finds *delivery manager*, *solutions architect*, *program manager*, *scrum master*, *engineering manager*, etc. Off-dictionary queries still expand via **acronyms** (PM, QA, SWE, UX, HR, CSM…) and **sibling roles** (e.g. "logistics coordinator" → logistics specialist / administrator / assistant), plus HireBase's semantic search. |
| Industry filter | Choose **All industries** or **Software & tech only**. The software filter keeps jobs whose industry, title, company or description signals tech (SaaS, engineering, cloud, data, AI, IT services, startups) and treats the software-focused boards (Greenhouse/Lever/Ashby/Workable companies, RemoteOK, Himalayas…) as tech by default. |
| Title + description ranking | Each job is scored on its title **and** its full description (phrase match, all-words match, related-role mentions). Each result is tagged `exact match`, `related role`, or `matches description`. |
| Remote vs Philippines | Choose Remote, Philippines, or Both. |
| PH city filter | Narrow Philippine results to a city. **Cebu** jobs can be on-site, hybrid or remote; everywhere else in the Philippines only **remote** jobs are shown. |
| Progress indicator | A progress bar with percent, sources checked and seconds elapsed while the boards are searched. |
| Salary filter | Minimum salary in USD or PHP, per month or per year. Salary is read from the API field or, failing that, from the description text. Option to keep jobs with no salary listed. |
| Years of experience | Enter your own years of experience and jobs that ask for **more** than that are hidden. The requirement is read from the API's experience field or from phrases like "3+ years of experience" in the description. Jobs that don't state a requirement are kept. Each result shows a tag such as `asks 3+ yrs exp`. |
| Entry-level filter | Keeps junior / entry-level / associate / 0–2 years postings and drops senior / lead / 5+ years ones. Uses the API's experience field when available. |
| Open to the Philippines | Keeps remote jobs that are worldwide, anywhere, global, Asia or APAC. |
| No citizenship required | Hides jobs mentioning citizenship, security clearance, work authorization, "must reside in", "US only", "no sponsorship", etc. It is a keyword heuristic, so always confirm on the posting. |
| Region-unclear tier (opt-in) | Off by default, your results stay strictly PH-eligible. Turn it on to also list remote jobs whose posting names a specific country (e.g. "Remote – US") in a **separate, clearly-labelled section** — many still accept PH applicants; verify each one. |
| Duplicate merge | The same job appearing on several boards is collapsed into one row (best-scored copy, salary filled in from whichever board had it), tagged `also on N more boards`. |
| Link buttons | One-click searches on 36 more boards (see below) with your keywords, city and entry-level filter pre-filled. |
| Excel tracker | Download an `.xlsx` with one row per job, a checklist, a status dropdown and a summary sheet. |
| Quota protection | RapidAPI calls are cached for 24 hours, capped locally per month, and stopped when the API reports few calls left. |

---

## Quick start

Requires **Python 3.9+** (developed on 3.12).

```bash
# 1. Get the code
git clone <your-repo-url>
cd JobSearch

# 2. (Optional but recommended) create a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 3. Install the only dependency (used for the Excel export)
pip install -r requirements.txt

# 4. (Optional) add API keys, see "API keys" below
copy .env.example .env          # Windows
# cp .env.example .env          # macOS / Linux
# then edit .env

# 5. Run
python jobsearch.py
```

Open **http://127.0.0.1:8000** in your browser. To use another port: `PORT=9000 python jobsearch.py` (PowerShell: `$env:PORT=9000; python jobsearch.py`).

The app works **without any API keys**. Keys only add Philippine job listings and a few more sources.

### Performance & the cache warmer

The app queries ~170 sources, including ~150 company career boards. Downloading and parsing those boards is the bulk of the time, and they are query-independent, so by default the app **warms them in the background** on startup and every ~55 minutes.

- **While the warmer is still running (the first ~minute after startup), a search is slow (~60 s).**
- Once warm, a fresh keyword takes roughly **15–25 s**; repeating a keyword is near-instant.
- In-memory cache lasts 1 hour (free feeds/boards); RapidAPI results are disk-cached 24 hours. Repeats use **no** API quota.
- To disable the background warmer (e.g. to avoid the recurring traffic): `WARM=0 python jobsearch.py`.

A progress bar shows percent, sources checked, and seconds elapsed during each search.

---

## Dependencies

| Package | Why | Install |
|---|---|---|
| Python 3.9+ | Runtime | https://www.python.org/downloads/ |
| `openpyxl` | Excel tracker export | `pip install -r requirements.txt` |

Everything else (HTTP server, networking, JSON, XML/RSS parsing) is the Python standard library. No Flask, no `requests`, no JavaScript build step: the UI is a single static [index.html](index.html).

---

## Data sources

### Free, no key needed (always on)

| Source | What it provides | Docs / site |
|---|---|---|
| Remotive | Remote jobs, 12 categories + keyword search | https://github.com/remotive-com/remote-jobs-api |
| RemoteOK | Remote jobs feed | https://remoteok.com/api |
| Jobicy | Remote jobs | https://jobicy.com/api |
| Himalayas | Remote jobs (search API + RSS) | https://himalayas.app/api |
| We Work Remotely | 8 category RSS feeds | https://weworkremotely.com/remote-job-rss-feed |
| Arbeitnow | Remote-flagged jobs | https://www.arbeitnow.com/api/job-board-api |
| The Muse | "Flexible / Remote" jobs across 14 categories | https://www.themuse.com/developers/api/v2 |
| Jobspresso, NoDesk, Real Work From Anywhere | RSS feeds | https://jobspresso.co, https://nodesk.co, https://www.realworkfromanywhere.com |
| Company career boards | ~100 remote-friendly employers on Greenhouse, Lever, Ashby and Workable public job-board APIs (edit the lists in `jobsearch.py`) | https://developers.greenhouse.io/job-board.html, https://github.com/lever/postings-api, https://developers.ashbyhq.com/docs/public-job-posting-api |

### Optional, needs a key

| Source | Covers | Free tier | Where to get a key |
|---|---|---|---|
| **JSearch** (RapidAPI) | Philippines + remote (Google for Jobs data) | 200 requests/month | https://rapidapi.com, search "JSearch" and subscribe to the Basic plan |
| **Active Jobs DB** (RapidAPI) | Philippines, with AI-extracted experience level, salary, work arrangement | 25 requests / 250 jobs per month | https://rapidapi.com, search "Active Jobs DB" |
| **HireBase Jobs Data** (RapidAPI) | Semantic / vector search (finds jobs related by *meaning*), remote + Philippines | 50 requests / 500 jobs per month | https://rapidapi.com, search "HireBase Jobs Data" |
| Jooble | Philippines | Free key on request | https://jooble.org/api/about |
| Adzuna | Remote jobs in US/UK/AU/CA/SG (no Philippines) | Free tier | https://developer.adzuna.com/ |

*Job Search Global (RapidAPI) was evaluated but not integrated: its free plan allows only 3 requests/month and it has no keyword search.*

### Search-link buttons (no API, they open the board's own search)

- **Philippines (16):** JobStreet PH, Indeed PH (+ entry level), LinkedIn (+ entry level), Kalibrr, Google Jobs, OnlineJobs.ph, Glassdoor PH, Jora PH, Talent.com PH, Jooble PH, Careerjet PH, Bossjob, Monster PH, PhilJobNet (DOLE).
- **Remote (20):** We Work Remotely, RemoteOK, Remote.co, FlexJobs, Wellfound, LinkedIn Remote (+ entry level), Indeed, Glassdoor, ZipRecruiter, SimplyHired, Dice, Built In, Working Nomads, Upwork, Jobgether, Remotive, Himalayas, Jooble, Google Jobs.

Most Philippine job boards have no public API, which is why they appear as links rather than listings. Some link formats are best-effort; if a site changes its URLs, edit `ph_links()` / `remote_links()` in `jobsearch.py`.

---

## API keys

1. Create a free account at https://rapidapi.com and subscribe to the **Basic (free)** plan of each API above. One RapidAPI key works for all of them. It is shown in the "X-RapidAPI-Key" field on any API's page.
2. Copy `.env.example` to `.env` and paste your key:

   ```ini
   RAPIDAPI_KEY=your_rapidapi_key_here
   RAPIDAPI_CAP_JSEARCH=180
   RAPIDAPI_CAP_ACTIVEJOBS=9
   RAPIDAPI_CAP_HIREBASE=45
   JOOBLE_KEY=
   ADZUNA_APP_ID=
   ADZUNA_APP_KEY=
   ```
3. Restart the app.

`.env` is listed in `.gitignore`. **Never commit your key.** If you ever expose it (for example in a screenshot), rotate it from your RapidAPI dashboard.

### How the quota guard works

Free plans have hard monthly limits, so every RapidAPI call goes through `rapid_call()` in [jobsearch.py](jobsearch.py):

- **24-hour disk cache** (`.cache/`): repeating a search costs nothing.
- **Local monthly cap** per API (`RAPIDAPI_CAP_<API>` in `.env`), stored in `.rapidapi_usage.json`. Set it slightly under your plan's limit.
- **Remaining-calls header:** if the API reports 5 or fewer calls left, it stops calling.
- **Error stop:** a 401/403/404/429 response stops further calls to that API for the month, so a wrong endpoint or exhausted plan is not retried.
- If a source is skipped, the reason shows at the top of the results and every other source still runs.

Each fresh keyword search costs roughly one call each on JSearch (Philippines), JSearch (remote), Active Jobs DB and HireBase (x2: remote + Philippines).

---

## Using the app

1. Enter keywords, pick **Remote**, **Philippines** or **Both**, optionally a PH city, and **All industries** vs **Software & tech only**.
2. Set filters: your years of experience, minimum salary (currency and period), entry-level only, open to Philippines, hide citizenship-required jobs, keep unlisted salaries, and (opt-in) also show region-unclear remote jobs.
3. Click **Search**. Results show title (linked to the posting), company, location, source, date, salary if known, match and arrangement tags, and the full URL. Region-unclear jobs, if enabled, appear in their own section below.
4. Click **Download Excel application tracker** to export what you found.

### The Excel tracker

| Sheet | Contents |
|---|---|
| **Applications** | One row per job with a clickable link, per-job checklist (Resume tailored, Cover letter, Applied, Followed up, Interview, Offer), a Status dropdown (To apply, Applied, Interview, Offer, Rejected, Withdrawn, No response), date applied and notes. Checked boxes and statuses are color-coded; headers are filterable. |
| **Summary** | Live counts per status and total applied (formulas update as you edit). |
| **Job boards to check** | Every search link from the page with a "checked" box. |

---

## How ranking works

1. The query is expanded with related roles from the `RELATED`, `MGMT` and `LEADERSHIP` dictionaries in `jobsearch.py`.
2. Each job is scored: exact title match (highest), related-role in title, phrase and all-words presence in the description, related-role mentions in the description.
3. Jobs below a relevance threshold are dropped, then filters apply (location, entry level, salary, citizenship), and results are sorted by score.

To add roles, edit those dictionaries. To add a company career board, append its slug to `GREENHOUSE`, `LEVER`, `ASHBY` or `WORKABLE`.

---

## Project structure

```
JobSearch/
├── jobsearch.py        # server, all sources, ranking, filters, quota guard, Excel export
├── index.html          # single-page UI (no build step)
├── requirements.txt    # openpyxl
├── .env.example        # template for your keys (copy to .env)
├── .gitignore          # excludes .env, cache, usage file, *.xlsx
└── README.md
```

Runtime files (git-ignored): `.env`, `.cache/`, `.rapidapi_usage.json`.

HTTP endpoints (local only, bound to `127.0.0.1`): `GET /` (UI), `GET /api/config`, `GET /api/search/start?q=...` (starts a search, returns an id), `GET /api/search/status?id=...` (progress, then the result), `GET /api/search?q=...` (blocking version), `POST /api/export`.

---

## Limitations

- The free job boards carry few entry-level and few Philippines-based listings; the Philippines coverage depends mostly on the RapidAPI sources and the link buttons.
- Salary data exists on only a minority of postings. Salaries in currencies other than USD/PHP are shown but not used by the salary filter.
- The "no citizenship" and "entry-level" filters are keyword heuristics over the posting text. Confirm on the actual posting before applying.
- Free APIs and boards change or disappear. A failing source is skipped and reported, and the rest still run.
- PHP/USD uses a fixed rate (`PHP_PER_USD = 57` in `jobsearch.py`); adjust it as needed.

---

## Responsible use

This tool calls public job-board APIs, RSS feeds and your own API keys, and links out to the original postings. It does not log in to any site or scrape protected pages. Respect each service's terms of use and rate limits, and keep your API keys private.

## License

Add a license of your choice (for example MIT) before publishing.

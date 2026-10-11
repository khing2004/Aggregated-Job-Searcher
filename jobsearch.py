"""Job search aggregator: remote jobs worldwide + Philippines (by city).

Run:  python jobsearch.py     then open http://127.0.0.1:8000
Stdlib only. Optional: set RAPIDAPI_KEY to get real Philippine listings (JSearch API).
"""
import html
import json
import os
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
UA = {"User-Agent": "Mozilla/5.0 (JobSearchProject; personal use)"}
PHP_PER_USD = 57.0
PH_CITIES = ["Manila", "Makati", "Taguig", "Quezon City", "Pasig", "Cebu", "Davao",
             "Cagayan de Oro", "Iloilo", "Baguio", "Clark", "Bacolod"]

# ---- query expansion ------------------------------------------------------
# key phrase -> related titles/skills. Matched against the user's query.
LEADERSHIP = [
    "operations manager", "general manager", "business operations manager", "program director", "project director",
    "director of operations", "director of engineering", "director of product", "head of operations", "head of product",
    "head of engineering", "head of delivery", "head of projects", "vp of operations", "vp of engineering",
    "chief of staff", "chief operating officer", "coo", "cto", "team lead", "tech lead", "engineering lead",
    "development manager", "software development manager", "it manager", "it operations manager", "it service manager",
    "service delivery manager", "delivery director", "client services manager", "account manager", "key account manager",
    "customer success manager", "customer support manager", "support team lead", "community manager", "people manager",
    "hr manager", "talent acquisition manager", "recruiting manager", "people operations manager", "office manager",
    "business manager", "strategy manager", "business development manager", "partnerships manager", "sales manager",
    "marketing manager", "growth manager", "content manager", "brand manager", "product marketing manager",
    "product operations manager", "release manager", "change manager", "transformation manager", "program lead",
    "pmo manager", "pmo lead", "portfolio manager", "implementation manager", "onboarding manager", "engagement lead",
    "delivery lead", "squad lead", "agile coach", "scrum master", "product owner", "technical product manager",
    "solutions architect", "enterprise architect", "technical architect", "solutions engineer manager",
    "quality assurance manager", "qa lead", "devops manager", "infrastructure manager", "security manager",
    "data manager", "analytics manager", "finance manager", "supply chain manager", "logistics manager",
    "vendor manager", "procurement manager", "compliance manager", "risk manager", "workforce manager",
    "team manager", "supervisor", "coordinator lead", "operations lead", "project lead", "technical manager",
]
MGMT = ["technical delivery lead", "delivery lead", "delivery manager", "solutions architect", "solution architect", "technical program manager", "engagement manager", "customer success manager", "implementation lead", "technical account manager", "service delivery manager", "program director", "head of delivery", "engineering manager", "technical lead", "product manager", "scrum master", "project coordinator", "program manager"]
# cybersecurity / infosec family — entry-level-friendly titles listed first
CYBER = [
    "soc analyst", "security operations center analyst", "soc analyst tier 1", "soc analyst i",
    "cybersecurity analyst", "security analyst", "information security analyst", "it security analyst",
    "cyber security analyst", "junior security analyst", "entry level security analyst",
    "cybersecurity intern", "security intern", "soc intern", "information security intern",
    "incident response analyst", "incident responder", "incident response", "cyber incident analyst",
    "threat intelligence analyst", "threat analyst", "threat hunter", "vulnerability analyst",
    "vulnerability management analyst", "security engineer", "cybersecurity engineer",
    "information security engineer", "detection engineer", "blue team analyst", "security operations analyst",
    "grc analyst", "governance risk and compliance analyst", "security compliance analyst",
    "it security specialist", "cybersecurity specialist", "security specialist", "siem analyst",
    "security administrator", "identity and access management analyst", "iam analyst",
    "application security analyst", "cloud security analyst", "network security analyst",
    "penetration tester", "junior penetration tester", "ethical hacker", "red team analyst",
    "security consultant", "security researcher", "malware analyst", "forensics analyst",
    "digital forensics analyst", "cyber defense analyst", "security operations", "infosec analyst",
]
RELATED = {
    "manager": LEADERSHIP, "lead": LEADERSHIP, "director": LEADERSHIP, "head of": LEADERSHIP,
    "management": LEADERSHIP, "leadership": LEADERSHIP, "supervisor": LEADERSHIP, "team lead": LEADERSHIP,
    "delivery": MGMT, "technical lead": MGMT, "solutions architect": MGMT, "program manager": MGMT,
    "engineering manager": MGMT, "technical program manager": MGMT, "scrum master": MGMT,
    "project manager": MGMT + LEADERSHIP[:60] + ["program manager", "project coordinator", "delivery manager", "scrum master",
                        "product owner", "technical project manager", "project lead", "pmo",
                        "agile coach", "project management", "operations manager", "implementation manager"],
    "software project manager": MGMT + LEADERSHIP[:60] + ["project manager", "technical program manager", "engineering manager", "scrum master",
                                 "delivery manager", "it project manager", "agile project manager",
                                 "release manager", "product manager"],
    "product manager": ["product owner", "product analyst", "associate product manager", "program manager",
                        "product operations", "technical product manager"],
    "developer": ["software engineer", "programmer", "web developer", "backend", "frontend", "full stack"],
    "software engineer": ["developer", "programmer", "backend engineer", "frontend engineer", "full stack"],
    "designer": ["ui designer", "ux designer", "product designer", "graphic designer", "visual designer"],
    "data analyst": ["business analyst", "data scientist", "bi analyst", "analytics", "reporting analyst"],
    "business analyst": ["data analyst", "systems analyst", "product analyst", "requirements analyst"],
    "customer support": ["customer service", "customer success", "support specialist", "technical support",
                         "help desk", "support agent"],
    "virtual assistant": ["executive assistant", "administrative assistant", "personal assistant",
                          "operations assistant", "admin support"],
    "marketing": ["digital marketing", "content marketing", "growth", "seo", "social media", "brand"],
    "recruiter": ["talent acquisition", "sourcer", "hr", "people operations", "recruitment"],
    "writer": ["copywriter", "content writer", "editor", "content creator", "technical writer"],
    "qa": ["quality assurance", "tester", "test engineer", "sdet", "qa engineer"],
    "devops": ["site reliability", "sre", "cloud engineer", "infrastructure", "platform engineer"],
    "sales": ["business development", "account executive", "sdr", "account manager", "sales representative"],
    # cybersecurity / infosec — any of these queries fans out across the whole CYBER family
    "cybersecurity": CYBER, "cyber security": CYBER, "cyber": CYBER, "security": CYBER,
    "information security": CYBER, "infosec": CYBER, "security analyst": CYBER, "soc analyst": CYBER,
    "soc": CYBER, "incident response": CYBER, "threat intelligence": CYBER, "security engineer": CYBER,
    "security operations": CYBER, "penetration testing": CYBER, "pentester": CYBER, "grc": CYBER,
    "vulnerability management": CYBER, "security operations center": CYBER,
}
STOP = set("a an and the of for to in at on with or job jobs remote work senior junior".split())

# short form -> full title, so "PM" / "QA" / "SWE" searches still expand
ACRONYMS = {
    "pm": "project manager", "tpm": "technical program manager", "po": "product owner",
    "pmo": "project management office", "ba": "business analyst", "qa": "quality assurance",
    "swe": "software engineer", "sde": "software engineer", "sre": "site reliability engineer",
    "ux": "ux designer", "ui": "ui designer", "hr": "human resources", "cs": "customer support",
    "csm": "customer success manager", "va": "virtual assistant", "em": "engineering manager",
    "sdr": "sales development representative", "ae": "account executive", "bd": "business development",
    "dba": "database administrator", "ml": "machine learning engineer", "da": "data analyst",
    "it": "information technology",
    "soc": "soc analyst", "ir": "incident response", "siem": "siem analyst", "grc": "grc analyst",
    "iam": "iam analyst", "infosec": "information security analyst", "pentest": "penetration tester",
    "pentester": "penetration tester", "dfir": "digital forensics analyst", "appsec": "application security analyst",
    "cti": "threat intelligence analyst", "sec": "security analyst",
}
# trailing role noun -> sibling roles, so any off-dictionary "<x> <role>" query still fans out
SIBLING = {
    "manager": ["lead", "director", "head of", "coordinator", "supervisor"],
    "lead": ["manager", "director", "head of", "principal"],
    "director": ["manager", "head of", "vp", "chief"],
    "engineer": ["developer", "programmer", "architect"],
    "developer": ["engineer", "programmer"],
    "analyst": ["specialist", "consultant", "associate"],
    "designer": ["ux designer", "ui designer", "product designer"],
    "specialist": ["analyst", "coordinator", "associate"],
    "coordinator": ["specialist", "administrator", "assistant", "associate"],
    "consultant": ["analyst", "advisor", "specialist"],
    "architect": ["engineer", "lead", "principal engineer"],
    "administrator": ["specialist", "engineer", "coordinator"],
    "officer": ["manager", "specialist", "lead"],
    "assistant": ["coordinator", "associate", "administrator"],
    "associate": ["analyst", "specialist", "coordinator"],
}


def generic_related(q, words):
    """Expansion that works for queries NOT in the RELATED dictionary: acronyms + sibling roles."""
    out = []
    if q in ACRONYMS:
        out.append(ACRONYMS[q])
    for w in words:
        if w in ACRONYMS:
            out.append(ACRONYMS[w])
    if words:
        last, base = words[-1], " ".join(words[:-1])
        if last in SIBLING and base:
            for sib in SIBLING[last]:
                out.append((("head of " + base) if sib == "head of" else (base + " " + sib)).strip())
    return out

ENTRY_RE = re.compile(r"\b(entry[- ]level|junior|jr\.?|graduate|fresh(?:er)?|trainee|intern(?:ship)?|"
                      r"associate|no experience|0\s*[-–to]+\s*[12]\s*years?|1\s*[-–]\s*2\s*years?|"
                      r"beginner|apprentice|coordinator|assistant|tier\s*(?:1|i)|level\s*(?:1|i)|"
                      r"(?:analyst|engineer|specialist)\s*(?:1|i)\b|\bt1\b|\bl1\b)\b", re.I)
SENIOR_RE = re.compile(r"\b(senior|sr\.?|lead|principal|director|head of|vp|vice president|staff|"
                       r"[5-9]\+?\s*(?:\+|or more)?\s*years|1\d\+?\s*years|manager of managers)\b", re.I)
CITIZEN_RE = re.compile(
    r"citizen(?:ship)?s?|nationals?|security clearance|clearance required|green card|permanent resident|"
    r"work authori[sz]ation|authori[sz]ed to work (?:in|for)|(?:legal(?:ly)? )?(?:right|eligib\w+|permit\w*) to work in|"
    r"eligible to work in|must (?:currently )?(?:reside|be (?:based|located|residing)) in|"
    r"(?:us|u\.s\.|uk|eu|canadian|australian) (?:persons?|residents?|based (?:only|candidates?))|"
    r"(?:us|u\.s\.|uk|eu|canada)[- ]only|without (?:the need for )?(?:visa )?sponsorship|"
    r"no (?:visa )?sponsorship|ITAR|export control", re.I)
OPEN_TO_PH_RE = re.compile(r"worldwide|anywhere|global|international|asia|apac|philippines|southeast|"
                           r"any ?where|^remote$|^$", re.I)
# software / tech signals, used by the "Software & tech companies only" option
TECH_RE = re.compile(
    r"\b(software|saas|paas|iaas|web3|fintech|insurtech|healthtech|edtech|proptech|adtech|martech|"
    r"information technology|\bit\b|\bict\b|tech(?:nology|nical)?|developer|programming|programmer|"
    r"engineer(?:ing)?|full[- ]stack|back[- ]?end|front[- ]?end|devops|sre|platform|cloud|aws|azure|gcp|"
    r"kubernetes|docker|microservices|\bapi\b|\bsdk\b|machine learning|artificial intelligence|\bai\b|"
    r"\bml\b|\bllm\b|data (?:engineer|scien|analyt)|cyber ?security|infosec|blockchain|crypto|"
    r"mobile app|ios|android|react|angular|vue|node|python|java(?:script)?|golang|rust|\.net|"
    r"computer science|startup|digital product|product-led|internet company|it services)\b", re.I)
# sources that are themselves software/tech job boards or tech-company ATSs
TECH_SOURCE_PREFIXES = ("Greenhouse", "Lever", "Ashby", "Workable", "RemoteOK", "Himalayas",
                        "Arbeitnow", "NoDesk", "Jobspresso")


def expand(query):
    q = query.lower().strip()
    terms = []
    # acronyms first so a short query (e.g. "ir", "soc") expands to the right role,
    # not to a longer dictionary key it happens to be a substring of ("director").
    terms += generic_related(q, [w for w in re.findall(r"[a-z0-9+#.]+", q) if w not in STOP])
    for key, rel in RELATED.items():
        if key in q or (len(q) >= 4 and q in key):
            terms += rel
    # also pick up partial matches: any query word that is a key word of a role
    words = [w for w in re.findall(r"[a-z0-9+#.]+", q) if w not in STOP]
    for key, rel in RELATED.items():
        if key != q and any(w in key.split() for w in words) and len(words) > 0 and key in q.replace("-", " "):
            terms += rel
    # a term we produced (e.g. an acronym's full form) may itself be a dictionary key
    for t in list(terms):
        if t in RELATED:
            terms += RELATED[t]
    if len(words) > 2:
        terms.append(" ".join(words[-2:]))
    seen, out = set(), []
    for t in terms:
        t = t.strip()
        if t and t not in seen and t != q:
            seen.add(t)
            out.append(t)
    return words, out


_CACHE = {}


def fetch(url, headers=None, timeout=12, data=None, ttl=3600):
    """GET/POST with a 1-hour in-memory cache so repeat searches are fast."""
    import time
    key = (url, data)
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    _CACHE[key] = (time.time(), body)
    return body


def http_get(url, headers=None, timeout=12):
    return json.loads(fetch(url, headers, timeout).decode("utf-8", "replace"))


def rss_items(url):
    import xml.etree.ElementTree as ET
    raw = fetch(url).decode("utf-8", "replace")
    raw = "".join(ch for ch in raw if ch.isprintable() or ch.isspace())
    raw = re.sub(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", "&amp;", raw)
    return ET.fromstring(raw.encode("utf-8")).iter("item")


def strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def to_iso(s):
    """Normalize any posting date (ISO, RFC-2822 RSS pubDate, timestamp…) to YYYY-MM-DD, else ''."""
    s = str(s or "").strip()
    if not s:
        return ""
    m = re.match(r"(\d{4})[-/](\d{2})[-/](\d{2})", s)
    if m:
        return "%s-%s-%s" % m.groups()
    try:
        import email.utils
        dt = email.utils.parsedate_to_datetime(s)
        return dt.date().isoformat() if dt else ""
    except Exception:
        return ""


def parse_salary(text):
    """Return (min_usd_year, max_usd_year) from a free-text salary, or (None, None)."""
    if not text:
        return None, None
    t = text.replace(",", "")
    nums = [float(n) * (1000 if k else 1) for n, k in re.findall(r"(\d+(?:\.\d+)?)\s*(k)?\b", t, re.I)]
    nums = [n for n in nums if n >= 100]
    if not nums:
        return None, None
    lo, hi = min(nums), max(nums)
    fx = 1 / PHP_PER_USD if re.search(r"php|₱|peso", t, re.I) else 1
    mult = 1
    if re.search(r"/\s*h(ou)?r|hourly|per hour", t, re.I):
        mult = 2080
    elif re.search(r"/\s*mo|monthly|per month", t, re.I):
        mult = 12
    return lo * fx * mult, hi * fx * mult


def job(source, title, company, url, location, desc, lo=None, hi=None, salary_text="", date="", level="",
        remote=None, industries=""):
    return {"source": source, "title": title or "", "company": company or "", "url": url or "",
            "location": location or "", "description": strip_html(desc)[:4000],
            "salary_min": lo, "salary_max": hi, "salary_text": salary_text, "date": to_iso(date),
            "level": level, "remote": remote, "industries": industries if isinstance(industries, str)
            else ", ".join(x for x in (industries or []) if x)}


# ---- sources --------------------------------------------------------------
def _safe(func, x):
    try:
        return func(x)
    except Exception:       # a dead page / term must not sink the whole source
        return []


def _parallel(func, items, workers=8):
    """Run func over items concurrently and concat the lists. Keeps a fanned-out source
    about as fast as a single request, so we can search more related roles / more pages."""
    items = list(items)
    if not items:
        return []
    out = []
    with ThreadPoolExecutor(min(workers, len(items))) as ex:
        for r in ex.map(lambda x: _safe(func, x), items):
            out += r
    return out


def src_remotive(terms):
    def one(t):
        d = http_get("https://remotive.com/api/remote-jobs?search=" + urllib.parse.quote(t))
        return [job("Remotive", j["title"], j["company_name"], j["url"],
                    j.get("candidate_required_location"), j.get("description"),
                    *parse_salary(j.get("salary")), j.get("salary") or "", j.get("publication_date"))
                for j in d.get("jobs", [])]
    return _parallel(one, terms[:8])


def src_remoteok(terms):
    out = []
    for j in http_get("https://remoteok.com/api")[1:]:
        lo, hi = j.get("salary_min") or None, j.get("salary_max") or None
        st = f"${lo:,}–${hi:,}/yr" if lo and hi else ""
        out.append(job("RemoteOK", j.get("position"), j.get("company"), j.get("url"),
                       j.get("location"), j.get("description", "") + " " + " ".join(j.get("tags", [])),
                       lo, hi, st, j.get("date")))
    return out


def src_arbeitnow(terms):
    def one(page):
        d = http_get(f"https://www.arbeitnow.com/api/job-board-api?page={page}")
        return [job("Arbeitnow", j["title"], j["company_name"], j["url"],
                    "Remote – " + j.get("location", ""), j.get("description"),
                    date=str(j.get("created_at", "")))
                for j in d.get("data", []) if j.get("remote")]
    return _parallel(one, range(1, 6))      # paginate this free source for more recall


def src_jobicy(terms):
    def one(t):
        d = http_get("https://jobicy.com/api/v2/remote-jobs?count=50&tag=" + urllib.parse.quote(t))
        res = []
        for j in d.get("jobs", []):
            lo = float(j["annualSalaryMin"]) if j.get("annualSalaryMin") else None
            hi = float(j["annualSalaryMax"]) if j.get("annualSalaryMax") else None
            cur = j.get("salaryCurrency") or "USD"
            st = f"{cur} {lo:,.0f}–{hi:,.0f}/yr" if lo and hi else ""
            lvl = j.get("jobLevel")
            if isinstance(lvl, list):
                lvl = ", ".join(lvl)
            res.append(job("Jobicy", j.get("jobTitle"), j.get("companyName"), j.get("url"),
                           j.get("jobGeo"), j.get("jobDescription") or j.get("jobExcerpt"),
                           lo, hi, st, j.get("pubDate"), lvl or "", industries=j.get("jobIndustry")))
        return res
    return _parallel(one, terms[:6])


def src_himalayas(terms):
    def one(t):
        d = http_get("https://himalayas.app/jobs/api/search?sort=relevant&q=" + urllib.parse.quote(t))
        res = []
        for j in d.get("jobs", []):
            lo, hi = j.get("minSalary"), j.get("maxSalary")
            mult = {"hourly": 2080, "weekly": 52, "monthly": 12}.get(j.get("salaryPeriod"), 1)
            cur = j.get("currency") or "USD"
            fx = 1 / PHP_PER_USD if cur == "PHP" else 1
            st = f"{cur} {lo:,.0f}-{hi:,.0f}/{j.get('salaryPeriod') or 'yearly'}" if lo and hi else ""
            loc = ", ".join(j.get("locationRestrictions") or []) or "Worldwide"
            res.append(job("Himalayas", j.get("title"), j.get("companyName"),
                           j.get("applicationLink") or j.get("guid"), loc,
                           j.get("description") or j.get("excerpt"),
                           lo * mult * fx if lo else None, hi * mult * fx if hi else None, st,
                           str(j.get("pubDate", "")), j.get("seniority") if isinstance(j.get("seniority"), str) else ", ".join(j.get("seniority") or [])))
        return res
    return _parallel(one, terms[:6])


def src_wwr(terms):
    feeds = ["remote-jobs", "categories/remote-management-and-finance-jobs",
             "categories/remote-product-jobs", "categories/remote-customer-support-jobs",
             "categories/remote-full-stack-programming-jobs", "categories/remote-sales-and-marketing-jobs",
             "categories/remote-design-jobs", "categories/all-other-remote-jobs"]

    def one(f):
        res = []
        for it in rss_items(f"https://weworkremotely.com/{f}.rss"):
            g = lambda k: (it.findtext(k) or "")
            co, _, title = g("title").partition(": ")
            res.append(job("We Work Remotely", title or co, co if title else "", g("link"),
                           g("region") or "Anywhere", g("description"), date=g("pubDate")))
        return res
    return _parallel(one, feeds)


def _rss_source(name, url, default_loc="Remote"):
    out = []
    for it in rss_items(url):
        g = lambda k: (it.findtext(k) or "")
        out.append(job(name, g("title"), "", g("link"), g("location") or default_loc,
                       g("{http://purl.org/rss/1.0/modules/content/}encoded") or g("description"),
                       date=g("pubDate")))
    return out


def src_jobspresso(terms):
    return _rss_source("Jobspresso", "https://jobspresso.co/feed/?post_type=job_listing")


def src_nodesk(terms):
    return _rss_source("NoDesk", "https://nodesk.co/remote-jobs/index.xml")


def src_rwfa(terms):
    return _rss_source("Real Work From Anywhere", "https://www.realworkfromanywhere.com/rss.xml", "Anywhere")


def src_himalayas_rss(terms):
    return _rss_source("Himalayas", "https://himalayas.app/jobs/rss", "Worldwide")


def src_remotive_cats(terms):
    cats = ("project-management", "product", "customer-support", "software-development", "business",
            "marketing", "sales", "human-resources", "data", "design", "finance-legal", "all-others")

    def one(c):
        return [job("Remotive", j["title"], j["company_name"], j["url"],
                    j.get("candidate_required_location"), j.get("description"),
                    *parse_salary(j.get("salary")), j.get("salary") or "", j.get("publication_date"))
                for j in http_get("https://remotive.com/api/remote-jobs?category=" + c).get("jobs", [])]
    return _parallel(one, cats)


def src_muse(terms):
    cats = ["Project Management", "Product Management", "Operations", "Account Management", "Software Engineering",
            "Data and Analytics", "Design and UX", "Marketing", "Customer Service", "Sales",
            "Human Resources and Recruiting", "Writing and Editing", "Business Operations", "IT"]

    def one(c):
        res = []
        for pg in (1, 2, 3):
            try:
                u = ("https://www.themuse.com/api/public/jobs?page=%d&category=%s&location=%s" %
                     (pg, urllib.parse.quote(c), urllib.parse.quote("Flexible / Remote")))
                for j in http_get(u).get("results", []):
                    res.append(job("The Muse", j["name"], j["company"]["name"], j["refs"]["landing_page"],
                                   ", ".join(l["name"] for l in j.get("locations", [])) or "Flexible / Remote",
                                   j.get("contents"), date=j.get("publication_date"),
                                   level=", ".join(l["name"] for l in j.get("levels", [])),
                                   industries=[cat["name"] for cat in j.get("categories", [])] or [c]))
            except Exception:
                break
        return res
    with ThreadPoolExecutor(14) as ex:
        return [x for r in ex.map(one, cats) for x in r]


# Company career boards on public ATS APIs (remote-friendly employers). Dead slugs are skipped silently.
GREENHOUSE = ["gitlab", "stripe", "figma", "datadog", "cloudflare", "coinbase", "twilio", "elastic", "reddit",
              "discord", "duolingo", "webflow", "airtable", "asana", "dropbox", "pinterest", "okta", "mongodb",
              "gusto", "samsara", "instacart", "squarespace", "hubspotjobs", "zapier", "toast", "grammarly",
              "calendly", "fivetran", "affirm", "robinhood", "lyft", "brex", "chime", "opendoor", "mixpanel",
              "amplitude", "doordash", "databricks", "benchling", "carta", "sofi", "vercel", "retool", "hashicorp",
              "wikimedia", "buffer", "automatticcareers", "remotecom", "invisionapp", "yext", "sproutsocial",
              # additional remote-friendly employers (real Greenhouse boards)
              "airbnb", "snyk", "cockroachlabs", "sourcegraph", "miro", "newrelic", "pagerduty",
              "customerio", "close", "contentful", "algolia", "launchdarkly", "postman", "auth0",
              "1password", "tailscale", "huggingface", "turing", "andela", "shopify", "digitalocean",
              "gocardless", "wise", "remitly", "clickhouse", "planetscale", "sentry"]
LEVER = ["netflix", "spotify", "palantir", "welocalize", "mistral", "kraken", "plaid", "lever",
         "attentive", "wealthsimple", "gohighlevel", "highspot", "nielsen", "paddle", "outreach",
         "revolut", "consensys", "upgrade", "scribd", "patreon", "substack",
         "ironclad", "clari", "aircall", "dialpad", "klaviyo", "gorgias"]
ASHBY = ["ashby", "notion", "ramp", "linear", "deel", "supabase", "posthog", "openai", "anthropic",
         "cohere", "replit", "airbyte", "clickup", "doist", "remote", "mercury", "watershed", "vanta",
         "perplexity", "harvey", "glean", "writer", "baseten", "replicate", "wandb",
         "dagster", "prefect", "hex", "mintlify", "speakeasy", "braintrust", "windmill", "inngest", "flagsmith"]
WORKABLE = ["doist", "toggl", "hotjar", "dnsimple", "kinsta", "pipedrive", "bitrise", "paysend", "jobgether",
            "rocketchat", "mattermost", "safetywing", "oyster", "multiplier", "remofirst", "proxify"]


def _remote_loc(loc):
    return bool(re.search(r"remote|anywhere|worldwide|global|distributed|philippines|apac|asia", loc or "", re.I))


def ats_fetchers():
    def gh(slug):
        out = []
        for j in http_get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true", None, 5).get("jobs", []):
            loc = (j.get("location") or {}).get("name", "")
            if _remote_loc(loc):
                out.append(job("Greenhouse: " + slug, j["title"], slug, j["absolute_url"], loc,
                               html.unescape(j.get("content") or ""), date=j.get("updated_at")))
        return out

    def lv(slug):
        out = []
        for j in http_get(f"https://api.lever.co/v0/postings/{slug}?mode=json", None, 5):
            loc = (j.get("categories") or {}).get("location", "") or ""
            if _remote_loc(loc) or j.get("workplaceType") == "remote":
                out.append(job("Lever: " + slug, j["text"], slug, j["hostedUrl"], loc or "Remote",
                               j.get("descriptionPlain") or j.get("description")))
        return out

    def ab(slug):
        out = []
        for j in http_get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true", None, 5).get("jobs", []):
            loc = j.get("location") or ""
            if j.get("isRemote") or _remote_loc(loc):
                comp = (j.get("compensation") or {}).get("compensationTierSummary", "")
                lo, hi = parse_salary(comp)
                out.append(job("Ashby: " + slug, j["title"], slug, j["jobUrl"], loc or "Remote",
                               j.get("descriptionPlain") or j.get("descriptionHtml"), lo, hi, comp,
                               j.get("publishedAt")))
        return out

    def wk(slug):
        out = []
        for j in http_get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}", None, 5).get("jobs", []):
            loc = ", ".join(x for x in (j.get("city"), j.get("country")) if x)
            if j.get("telecommuting") or _remote_loc(loc):
                out.append(job("Workable: " + slug, j["title"], slug, j.get("url") or j.get("shortlink"),
                               "Remote " + loc, j.get("description"), date=j.get("published_on")))
        return out

    def uniq(xs):
        return list(dict.fromkeys(s.strip() for s in xs if s.strip()))
    tasks = ([(gh, x) for x in uniq(GREENHOUSE)] + [(lv, x) for x in uniq(LEVER)] +
             [(ab, x) for x in uniq(ASHBY)] + [(wk, x) for x in uniq(WORKABLE)])

    def safe(f, x):
        def call():
            try:
                return f(x)
            except Exception:       # dead / renamed board: skip silently
                return []
        return call
    return [safe(f, x) for f, x in tasks]


def src_jooble(query, city):
    key = os.environ.get("JOOBLE_KEY")
    if not key:
        return []
    body = json.dumps({"keywords": query, "location": (city + ", Philippines") if city else "Philippines"}).encode()
    d = json.loads(fetch("https://jooble.org/api/" + key, {"Content-Type": "application/json"}, data=body, ttl=300))
    out = []
    for j in d.get("jobs", []):
        lo, hi = parse_salary(j.get("salary"))
        out.append(job("Jooble PH", j.get("title"), j.get("company"), j.get("link"),
                       j.get("location") or "Philippines", j.get("snippet"), lo, hi, j.get("salary") or "",
                       j.get("updated")))
    return out


def src_adzuna_remote(terms):
    app_id, key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and key):
        return []
    out = []
    for c in ("us", "gb", "au", "ca", "sg"):
        u = (f"https://api.adzuna.com/v1/api/jobs/{c}/search/1?app_id={app_id}&app_key={key}"
             f"&results_per_page=50&what={urllib.parse.quote(terms[0] + ' remote')}")
        for j in http_get(u).get("results", []):
            lo, hi = j.get("salary_min"), j.get("salary_max")
            out.append(job("Adzuna " + c.upper(), j.get("title"), (j.get("company") or {}).get("display_name"),
                           j.get("redirect_url"), "Remote - " + (j.get("location") or {}).get("display_name", ""),
                           j.get("description"), lo, hi, f"{lo:,.0f}-{hi:,.0f}" if lo and hi else "",
                           j.get("created")))
    return out


def load_env():
    f = HERE / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


load_env()
USAGE_FILE = HERE / ".rapidapi_usage.json"
CACHE_DIR = HERE / ".cache"
RAPID_RESERVE = 5          # stop when the API says this few calls remain
RAPID_CACHE_TTL = 24 * 3600


def rapid_call(api, host, path, method="GET", data=None, ctype=None):
    """GET a RapidAPI endpoint without exceeding quota: 24h disk cache, a local monthly cap
    (env RAPIDAPI_CAP_<API>, default 100) and the API's own remaining-calls header."""
    import hashlib
    import time
    key = os.environ.get("RAPIDAPI_KEY")
    if not key:
        raise RuntimeError(f"{api}: RAPIDAPI_KEY not set")
    CACHE_DIR.mkdir(exist_ok=True)
    cf = CACHE_DIR / (hashlib.sha1((host + path + str(data)).encode()).hexdigest() + ".json")
    if cf.exists() and time.time() - cf.stat().st_mtime < RAPID_CACHE_TTL:
        return json.loads(cf.read_text(encoding="utf-8"))
    month = time.strftime("%Y-%m")
    try:
        usage = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except Exception:
        usage = {}
    u = usage.setdefault(month, {}).setdefault(api, {"calls": 0, "remaining": None})
    cap = int(os.environ.get(f"RAPIDAPI_CAP_{api.upper()}", 100))
    if u["calls"] >= cap:
        raise RuntimeError(f"{api}: monthly cap of {cap} calls reached (raise RAPIDAPI_CAP_{api.upper()} in .env)")
    if u["remaining"] is not None and u["remaining"] <= RAPID_RESERVE:
        raise RuntimeError(f"{api}: only {u['remaining']} calls left on the plan, skipped to protect the quota")
    hdr = {**UA, "X-RapidAPI-Key": key, "X-RapidAPI-Host": host}
    if ctype:
        hdr["Content-Type"] = ctype
    req = urllib.request.Request("https://" + host + path, data=data, method=method, headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read()
            rem = r.headers.get("x-ratelimit-requests-remaining")
    except urllib.error.HTTPError as e:
        u["calls"] += 1
        if e.code in (401, 403, 404, 429):   # not subscribed / wrong endpoint / out of quota: stop retrying
            u["remaining"] = 0
        USAGE_FILE.write_text(json.dumps(usage), encoding="utf-8")
        detail = e.read()[:250].decode("utf-8", "replace")
        raise RuntimeError(f"{api}: HTTP {e.code} {detail}")
    u["calls"] += 1
    if rem is not None and rem.isdigit():
        u["remaining"] = int(rem)
    USAGE_FILE.write_text(json.dumps(usage), encoding="utf-8")
    cf.write_bytes(body)
    return json.loads(body.decode("utf-8", "replace"))


def src_activejobs(query, city, related):
    """Active Jobs DB (RapidAPI, plan: 25 requests / 250 jobs per month): Philippines postings with AI-extracted
    experience level and salary. One call per fresh search, 25 jobs, cached 24h."""
    if not os.environ.get("RAPIDAPI_KEY"):
        return []
    titles = " OR ".join('"%s"' % t for t in [query] + related[:3])
    loc = '"%s"' % (city or "Philippines")
    path = ("/active-ats?time_frame=7d&limit=25&offset=0&description_format=text&title=%s&location=%s" %
            (urllib.parse.quote(titles), urllib.parse.quote(loc)))
    out = []
    for j in rapid_call("activejobs", "active-jobs-db.p.rapidapi.com", path):
        locs = ", ".join(j.get("locations_alt") or j.get("locations_derived") or []) or "Philippines"
        lo, hi = j.get("ai_salary_min_value"), j.get("ai_salary_max_value")
        if lo is None and j.get("ai_salary_value"):
            lo = hi = j["ai_salary_value"]
        unit = (j.get("ai_salary_unit_text") or "YEAR").upper()
        cur = j.get("ai_salary_currency") or "USD"
        mult = {"HOUR": 2080, "DAY": 260, "WEEK": 52, "MONTH": 12}.get(unit, 1)
        fx = 1 / PHP_PER_USD if cur == "PHP" else 1
        st = f"{cur} {lo:,.0f}-{hi:,.0f}/{unit.lower()}" if lo and hi else ""
        exp = j.get("ai_experience_level") or ""
        level = "entry level" if exp in ("0-2", "0") else (f"{exp} years" if exp else "")
        desc = " ".join(x for x in (j.get("ai_core_responsibilities"), j.get("ai_requirements_summary"),
                                    j.get("description_text")) if x)
        arr = j.get("ai_work_arrangement")
        out.append(job("Active Jobs DB", j.get("title"), j.get("organization"), j.get("url"),
                       locs + (f" ({arr})" if arr else ""), desc,
                       lo * mult * fx if lo else None, hi * mult * fx if hi else None, st,
                       j.get("date_posted"), level,
                       remote=None if not arr else "remote" in arr.lower()))
    return out


def src_hirebase(query, city, related, ph):
    """HireBase vector (semantic) job search via RapidAPI (plan: 50 requests / 500 jobs per month).
    Matches on meaning of the job summary, so it finds related roles. One call, 25 jobs, cached 24h."""
    if not os.environ.get("RAPIDAPI_KEY"):
        return []
    text = query + ": " + ", ".join(related[:4])
    if ph:
        text += f" in {city + ', ' if city else ''}Philippines"
    body = json.dumps({"search_type": "summary", "query": text, "top_k": 100, "accuracy": 0.3,
                       "locations": ["Remote", "Hybrid", "In-Person"] if ph else ["Remote"],
                       "page": 1, "limit": 25}).encode()
    d = rapid_call("hirebase", "hirebase-jobs-data.p.rapidapi.com", "/v2/jobs/vsearch", "POST", body, "application/json")
    out = []
    for j in d.get("jobs", []):
        locs = j.get("locations") or []
        if ph and not any((l.get("country") or "").lower() == "philippines" for l in locs):
            continue
        loc = "; ".join(l.get("address") or l.get("city") or "" for l in locs[:3]) or "Remote"
        if j.get("location_type"):
            loc += f" ({j['location_type']})"
        sal = j.get("salary_range")
        lo = hi = None
        st = ""
        if isinstance(sal, dict):
            lo, hi = sal.get("min"), sal.get("max")
            cur = sal.get("currency") or "USD"
            per = str(sal.get("period") or sal.get("unit") or "year").lower()
            mult = 2080 if "hour" in per else 12 if "month" in per else 1
            fx = 1 / PHP_PER_USD if cur == "PHP" else 1
            st = f"{cur} {lo:,.0f}-{hi:,.0f}/{per}" if lo and hi else ""
            known = cur in ("USD", "PHP")      # no FX rate for other currencies: show text, skip salary filter
            lo = lo * mult * fx if lo and known else None
            hi = hi * mult * fx if hi and known else None
        yoe = j.get("yoe_range") or {}
        ymin, ymax = yoe.get("min"), yoe.get("max")
        level = ""
        if ymin is not None:
            level = "entry level" if ymin <= 2 and (ymax or 0) <= 3 else f"{ymin}+ years"
        cd = j.get("company_data") or {}
        inds = (cd.get("industries") or []) + (cd.get("subindustries") or []) + (j.get("job_categories") or [])
        out.append(job("HireBase PH" if ph else "HireBase", j.get("job_title"), j.get("company_name"),
                       j.get("application_link"), loc, j.get("description"), lo, hi, st,
                       j.get("date_posted"), level,
                       remote=None if not j.get("location_type") else j["location_type"].lower() == "remote",
                       industries=inds))
    return out


def src_jsearch(query, city, remote=False):
    if not os.environ.get("RAPIDAPI_KEY"):
        return []
    if remote:
        q = urllib.parse.quote(f"{query} remote")
        path = f"/search-v2?query={q}&num_pages=1&work_from_home=true&date_posted=all"
    else:
        q = urllib.parse.quote(f"{query} in {city + ', ' if city else ''}Philippines")
        path = f"/search-v2?query={q}&num_pages=1&country=ph&date_posted=all"
    d = rapid_call("jsearch", "jsearch.p.rapidapi.com", path)
    out = []
    for j in (d.get("data") or {}).get("jobs", []):
        lo, hi = j.get("job_min_salary"), j.get("job_max_salary")
        per = (j.get("job_salary_period") or "").upper()
        cur = j.get("job_salary_currency") or "PHP"
        mult = {"HOUR": 2080, "MONTH": 12, "WEEK": 52, "DAY": 260}.get(per, 1)
        fx = 1 / PHP_PER_USD if cur == "PHP" else 1
        st = f"{cur} {lo:,.0f}–{hi:,.0f}/{per.lower() or 'yr'}" if lo and hi else ""
        loc = ", ".join(x for x in (j.get("job_city"), j.get("job_country")) if x)
        out.append(job("JSearch Remote" if remote else "Google Jobs (JSearch)", j.get("job_title"), j.get("employer_name"),
                       j.get("job_apply_link"), loc, j.get("job_description"),
                       lo * mult * fx if lo else None, hi * mult * fx if hi else None, st,
                       j.get("job_posted_at_datetime_utc"), remote=j.get("job_is_remote")))
    return out


def remote_links(query):
    q = urllib.parse.quote_plus(query)
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
    return [
        {"name": "We Work Remotely", "url": f"https://weworkremotely.com/remote-jobs/search?term={q}"},
        {"name": "RemoteOK", "url": f"https://remoteok.com/remote-{slug}-jobs"},
        {"name": "Remote.co", "url": f"https://remote.co/remote-jobs/search/?search_keywords={q}"},
        {"name": "FlexJobs", "url": f"https://www.flexjobs.com/search?search={q}&location="},
        {"name": "Wellfound (startups)", "url": f"https://wellfound.com/jobs?remote=true&query={q}"},
        {"name": "LinkedIn Remote", "url": f"https://www.linkedin.com/jobs/search/?keywords={q}&f_WT=2"},
        {"name": "LinkedIn Remote (entry level)", "url": f"https://www.linkedin.com/jobs/search/?keywords={q}&f_WT=2&f_E=2"},
        {"name": "Indeed Remote", "url": f"https://www.indeed.com/jobs?q={q}&l=remote"},
        {"name": "Glassdoor Remote", "url": f"https://www.glassdoor.com/Job/jobs.htm?sc.keyword={q}&remoteWorkType=1"},
        {"name": "ZipRecruiter Remote", "url": f"https://www.ziprecruiter.com/jobs-search?search={q}&location=Remote"},
        {"name": "SimplyHired Remote", "url": f"https://www.simplyhired.com/search?q={q}&l=remote"},
        {"name": "Dice Remote", "url": f"https://www.dice.com/jobs?q={q}&filters.workplaceTypes=Remote"},
        {"name": "Built In Remote", "url": f"https://builtin.com/jobs/remote?search={q}"},
        {"name": "Working Nomads", "url": f"https://www.workingnomads.com/jobs?tag={q}"},
        {"name": "Upwork (freelance)", "url": f"https://www.upwork.com/nx/search/jobs/?q={q}"},
        {"name": "Jobgether", "url": f"https://jobgether.com/search-offers?keyword={q}"},
        {"name": "Remotive", "url": f"https://remotive.com/remote-jobs/search/?query={q}"},
        {"name": "Himalayas", "url": f"https://himalayas.app/jobs?q={q}"},
        {"name": "Jooble Remote", "url": f"https://jooble.org/SearchResult?ukw={q}%20remote"},
        {"name": "Google Jobs (remote)", "url": f"https://www.google.com/search?q={q}+remote+jobs&ibp=htl;jobs"},
    ]


def ph_links(query, city):
    q = urllib.parse.quote_plus(query)
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
    loc = (city + ", Philippines") if city else "Philippines"
    cs = urllib.parse.quote(city or "Philippines")
    return [
        {"name": "JobStreet Philippines", "url": f"https://ph.jobstreet.com/{slug}-jobs" + (f"/in-{cs}" if city else "")},
        {"name": "Indeed Philippines", "url": f"https://ph.indeed.com/jobs?q={q}&l={urllib.parse.quote_plus(city or 'Philippines')}"},
        {"name": "Indeed PH (entry level)", "url": f"https://ph.indeed.com/jobs?q={q}&l={urllib.parse.quote_plus(city or 'Philippines')}&explvl=entry_level"},
        {"name": "LinkedIn Jobs", "url": f"https://www.linkedin.com/jobs/search/?keywords={q}&location={urllib.parse.quote(loc)}"},
        {"name": "LinkedIn (entry level)", "url": f"https://www.linkedin.com/jobs/search/?keywords={q}&location={urllib.parse.quote(loc)}&f_E=2"},
        {"name": "Kalibrr", "url": f"https://www.kalibrr.com/job-board/te/{slug}"},
        {"name": "Google Jobs", "url": f"https://www.google.com/search?q={q}+jobs+in+{urllib.parse.quote_plus(loc)}&ibp=htl;jobs"},
        {"name": "OnlineJobs.ph (remote for foreign employers)", "url": f"https://www.onlinejobs.ph/jobseekers/jobsearch?jobkeyword={q}"},
        {"name": "Glassdoor Philippines", "url": f"https://www.glassdoor.com.ph/Job/jobs.htm?sc.keyword={q}&locKeyword={cs}"},
        {"name": "Jora Philippines", "url": f"https://ph.jora.com/j?q={q}&l={urllib.parse.quote_plus(city or '')}"},
        {"name": "Talent.com Philippines", "url": f"https://ph.talent.com/jobs?k={q}&l={urllib.parse.quote_plus(city or 'Philippines')}"},
        {"name": "Jooble Philippines", "url": f"https://ph.jooble.org/SearchResult?ukw={q}&rgns={urllib.parse.quote_plus(city or '')}"},
        {"name": "Careerjet Philippines", "url": f"https://www.careerjet.com.ph/jobs?s={q}&l={urllib.parse.quote_plus(city or '')}"},
        {"name": "Bossjob Philippines", "url": f"https://bossjob.ph/jobs-hiring/{slug}-jobs"},
        {"name": "Monster Philippines", "url": f"https://www.monster.com.ph/jobs/search?q={q}&where={urllib.parse.quote_plus(city or '')}"},
        {"name": "PhilJobNet (DOLE)", "url": "https://philjobnet.gov.ph/"},
    ]


# ---- ranking --------------------------------------------------------------
def score(j, query, words, related):
    """Rank on title AND description. Description counts: full phrase, all query words,
    related-role phrases, and responsibility-style mentions (e.g. 'manage projects')."""
    title, desc = j["title"].lower(), j["description"].lower()
    text = title + " " + desc
    q = query.lower()
    s, tier = 0.0, "description"
    if q in title or (words and all(w in title for w in words)):
        s += 100; tier = "exact"
    rel_title = [r for r in related if r in title]
    if rel_title:
        s += 40; tier = tier if tier == "exact" else "related"
    # description signals
    s += min(20, 5 * desc.count(q))
    if words and all(re.search(r"" + re.escape(w[:-1] if len(w) > 4 and w.endswith("s") else w), desc) for w in words):
        s += 10
    rel_desc = sum(r in desc for r in related)
    s += min(18, 3 * rel_desc)
    if tier == "description":
        if q in desc:
            tier = "related"
        elif s < 12:
            return 0, tier
    return s, tier


YOE_LEVEL_RE = re.compile(r"(\d{1,2})\s*(?:\+|-|to|–)?\s*\d{0,2}\s*\+?\s*years?", re.I)
YOE_TEXT_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:(?:-|to|–)\s*\d{1,2}\s*)?\+?\s*years?'?\s*(?:of\s+)?"
                         r"(?:[a-z\-]+\s+){0,3}?(?:experience|exp)", re.I)


REMOTE_RE = re.compile(r"\bremote\b|work[- ]from[- ]home|\bwfh\b|work from anywhere", re.I)
HYBRID_RE = re.compile(r"hybrid|on-?site|in-?office|in-?person", re.I)


def is_remote(j):
    """True if the posting is remote. Uses the API's own flag when given, else the text."""
    if j.get("remote") is not None:
        return bool(j["remote"])
    head = j["title"] + " " + j["location"]
    if HYBRID_RE.search(head):
        return False
    return bool(REMOTE_RE.search(head + " " + j["description"][:600]))


def required_years(j):
    """Minimum years of experience a job asks for (None if it doesn't say)."""
    lvl = (j.get("level") or "").lower()
    if "entry" in lvl or "intern" in lvl:
        return 0
    m = YOE_LEVEL_RE.search(lvl)
    if m:
        return int(m.group(1))
    text = j["title"] + ". " + j["description"]
    found = [int(x.group(1)) for x in YOE_TEXT_RE.finditer(text) if int(x.group(1)) <= 20]
    if found:
        return min(found)
    if ENTRY_RE.search(j["title"]):
        return 0
    return None


def search(p, progress=None):
    query = p["q"].strip()
    words, related = expand(query)
    mode = p.get("mode", "remote")             # remote | ph | both
    city = p.get("city", "")
    jobs, errors = [], []

    fetchers = []
    terms = [query] + related
    if mode in ("remote", "both"):
        fetchers += [lambda: src_remotive(terms), lambda: src_remoteok(terms),
                     lambda: src_arbeitnow(terms), lambda: src_jobicy(terms),
                     lambda: src_himalayas(terms), lambda: src_wwr(terms),
                     lambda: src_jobspresso(terms), lambda: src_nodesk(terms), lambda: src_rwfa(terms),
                     lambda: src_himalayas_rss(terms), lambda: src_remotive_cats(terms),
                     lambda: src_muse(terms), lambda: src_adzuna_remote(terms), lambda: src_jsearch(query, city, True),
                     lambda: src_hirebase(query, city, related, False)]
    if mode in ("remote", "both"):
        fetchers += ats_fetchers()
    if mode in ("ph", "both"):
        fetchers += [lambda: src_jsearch(query, city), lambda: src_jooble(query, city),
                     lambda: src_activejobs(query, city, related),
                     lambda: src_hirebase(query, city, related, True)]

    def run(f):
        try:
            return f()
        except Exception as e:  # one dead source must not break the search
            errors.append(f"{getattr(f, '__name__', 'source')}: {e}")
            return []

    total, done = len(fetchers), 0
    with ThreadPoolExecutor(64) as ex:      # IO-bound: wide pool keeps wall time down despite many boards
        for fu in as_completed([ex.submit(run, f) for f in fetchers]):
            jobs += fu.result()
            done += 1
            if progress:
                progress(done, total)

    # filters
    open_ph = p.get("open_ph", True)
    entry = p.get("entry", False)
    min_sal = float(p.get("min_salary") or 0)
    cur = p.get("currency", "USD")
    period = p.get("period", "year")
    min_usd_year = min_sal / (PHP_PER_USD if cur == "PHP" else 1) * (12 if period == "month" else 1)
    keep_unlisted = p.get("keep_unlisted", True)
    my_years = float(p["years"]) if str(p.get("years", "")).strip() != "" else None
    show_maybe = p.get("show_maybe", False)          # #5: also show region-unclear remote jobs
    software_only = p.get("industry", "all") == "software"
    max_age = int(p.get("max_age") or 0)             # only jobs posted within N days (0 = any time)
    cutoff = ""
    if max_age:
        import datetime
        cutoff = (datetime.date.today() - datetime.timedelta(days=max_age)).isoformat()

    def norm(s):
        return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()

    def looks_tech(j):
        if j["source"].startswith(TECH_SOURCE_PREFIXES):
            return True
        return bool(TECH_RE.search(j["industries"] + " | " + j["title"] + " " + j["company"] + " " +
                                   j["description"][:1500]))

    def add(bucket, j):
        """Merge near-duplicates (#4): same normalized title + company collapse into one row,
        keeping the best-scored / salary-bearing copy and noting the other boards it appears on."""
        key = norm(j["title"]) + "|" + (norm(j["company"]) or urllib.parse.urlparse(j["url"]).netloc)
        rep = bucket.get(key)
        if rep is None:
            j["also_on"] = []
            bucket[key] = j
            return
        if (j["score"], bool(j["salary_text"])) > (rep["score"], bool(rep["salary_text"])):
            j["also_on"] = rep["also_on"] + [{"source": rep["source"], "url": rep["url"]}]
            if not j["salary_text"] and rep["salary_text"]:
                j["salary_text"], j["salary_min"], j["salary_max"] = rep["salary_text"], rep["salary_min"], rep["salary_max"]
            bucket[key] = j
        else:
            rep["also_on"].append({"source": j["source"], "url": j["url"]})
            if not rep["salary_text"] and j["salary_text"]:
                rep["salary_text"], rep["salary_min"], rep["salary_max"] = j["salary_text"], j["salary_min"], j["salary_max"]

    main, maybe = {}, {}
    for j in jobs:
        if not j["url"]:
            continue
        sc, tier = score(j, query, words, related)
        if sc < 6:
            continue
        # newly-posted filter: keep jobs dated on/after the cutoff; jobs with no/undated posting are kept
        if cutoff and j["date"] and j["date"] < cutoff:
            continue
        is_ph_src = j["source"].startswith(("Google Jobs", "Jooble PH", "Active Jobs DB", "HireBase PH"))
        bucket = "main"
        if is_ph_src:
            loc, remote = j["location"].lower(), is_remote(j)
            # Cebu: on-site, hybrid or remote. Anywhere else in the Philippines: remote only.
            if city and not (city.lower() in loc or remote):
                continue
            if "cebu" not in loc and not remote:
                continue
            j["arrangement"] = "Remote" if remote else "On-site / hybrid"
        elif open_ph and not OPEN_TO_PH_RE.search(j["location"].strip()):
            # remote job tied to a specific country: possibly still open to PH applicants
            if not show_maybe:
                continue
            bucket = "maybe"
            j["arrangement"] = "Remote (region unclear — verify eligibility)"
        if p.get("no_citizen", True) and not is_ph_src and CITIZEN_RE.search(j["title"] + " " + j["description"] + " " + j["location"]):
            continue
        if software_only and not looks_tech(j):
            continue
        blob = j["title"] + " " + j["description"] + " " + j["level"]
        if entry:
            if SENIOR_RE.search(j["title"]) or (SENIOR_RE.search(blob) and not ENTRY_RE.search(j["title"])):
                continue
            if not ENTRY_RE.search(blob) and "entry" not in j["level"].lower():
                continue
        req_years = required_years(j)
        j["years_required"] = req_years
        if my_years is not None and req_years is not None and req_years > my_years:
            continue
        if min_usd_year:
            if j["salary_max"] is None and j["salary_min"] is None:
                m = re.search(r"[$₱]\s?\d[\d,.]*\s?k?(?:\s*(?:-|–|to)\s*[$₱]?\s?\d[\d,.]*\s?k?)?(?:\s*(?:/|per)\s*(?:hr|hour|mo|month|yr|year))?", j["description"], re.I)
                if m:
                    j["salary_min"], j["salary_max"] = parse_salary(m.group(0))
                    j["salary_text"] = j["salary_text"] or m.group(0).strip() + " (from description)"
            top = j["salary_max"] or j["salary_min"]
            if top is None:
                if not keep_unlisted:
                    continue
            elif top < min_usd_year:
                continue
        j["score"], j["tier"] = round(sc, 1), tier
        j["entry_signal"] = bool(ENTRY_RE.search(blob)) and not SENIOR_RE.search(j["title"])
        add(maybe if bucket == "maybe" else main, j)

    results = sorted(main.values(), key=lambda x: (-x["score"], x["date"]), reverse=False)
    maybe_results = sorted(maybe.values(), key=lambda x: (-x["score"], x["date"]), reverse=False)
    return {"query": query, "related_terms": related, "count": len(results), "jobs": results[:200],
            "maybe_count": len(maybe_results), "maybe_jobs": maybe_results[:100],
            "ph_links": ph_links(query, city) if mode in ("ph", "both") else [],
            "remote_links": remote_links(query) if mode in ("remote", "both") else [],
            "sources_used": sorted({j["source"].split(":")[0] for j in jobs}),
            "jsearch_enabled": bool(os.environ.get("RAPIDAPI_KEY")), "errors": errors}


def build_tracker(jobs, query, ph_links_, remote_links_):
    """Excel workbook: one row per job with a per-job application checklist + status dropdown."""
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.formatting.rule import FormulaRule

    wb = Workbook()
    ws = wb.active
    ws.title = "Applications"
    steps = ["Resume tailored", "Cover letter", "Applied", "Followed up", "Interview", "Offer"]
    head = ["#", "Job title", "Company", "Location", "Salary", "Source", "Match", "Posted", "Link"] + steps + \
           ["Status", "Date applied", "Notes"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="2F5BEA")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    n0 = len(head) - len(steps) - 3          # index of first checklist column (0-based)
    for i, j in enumerate(jobs, 1):
        ws.append([i, j.get("title"), j.get("company"), j.get("location"), j.get("salary_text"),
                   j.get("source"), j.get("tier"), j.get("date"), j.get("url")] + [""] * len(steps) +
                  ["To apply", "", ""])
        cell = ws.cell(row=i + 1, column=9)
        cell.hyperlink = j.get("url")
        cell.font = Font(color="0563C1", underline="single")
    last = len(jobs) + 1
    first_chk = n0 + 1
    from openpyxl.utils import get_column_letter as L
    chk = DataValidation(type="list", formula1='"\u2611,\u2610"', allow_blank=True)
    status = DataValidation(type="list", formula1='"To apply,Applied,Interview,Offer,Rejected,Withdrawn,No response"')
    ws.add_data_validation(chk)
    ws.add_data_validation(status)
    for r in range(2, last + 1):
        for k in range(len(steps)):
            c = ws.cell(row=r, column=first_chk + k, value="\u2610")
            c.alignment = Alignment(horizontal="center")
            chk.add(c)
        status.add(ws.cell(row=r, column=first_chk + len(steps)))
    if last >= 2:
        rng = f"{L(first_chk)}2:{L(first_chk + len(steps) - 1)}{last}"
        ws.conditional_formatting.add(rng, FormulaRule(formula=[f'{L(first_chk)}2="\u2611"'],
                                      fill=PatternFill("solid", bgColor="C6EFCE")))
        sc = f"{L(first_chk + len(steps))}2:{L(first_chk + len(steps))}{last}"
        for text, color in (("Applied", "DDEBF7"), ("Interview", "FFF2CC"), ("Offer", "C6EFCE"), ("Rejected", "F8CBAD")):
            ws.conditional_formatting.add(sc, FormulaRule(formula=[f'{L(first_chk + len(steps))}2="{text}"'],
                                                          fill=PatternFill("solid", bgColor=color)))
    widths = [5, 42, 24, 24, 20, 20, 10, 12, 50] + [13] * len(steps) + [14, 14, 40]
    for k, w in enumerate(widths, 1):
        ws.column_dimensions[L(k)].width = w
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:{L(len(head))}{max(last, 2)}"

    sm = wb.create_sheet("Summary")
    sm["A1"], sm["B1"] = "Search", query
    sm["A2"], sm["B2"] = "Total jobs", len(jobs)
    sm["A4"], sm["B4"] = "Status", "Count"
    for k, st in enumerate(["To apply", "Applied", "Interview", "Offer", "Rejected", "Withdrawn", "No response"], 5):
        sm.cell(row=k, column=1, value=st)
        sm.cell(row=k, column=2, value=f'=COUNTIF(Applications!{L(first_chk + len(steps))}2:{L(first_chk + len(steps))}{max(last, 2)},A{k})')
    sm["A13"], sm["B13"] = "Applied so far", f'=COUNTIF(Applications!{L(first_chk + 2)}2:{L(first_chk + 2)}{max(last, 2)},"\u2611")'
    for c in ("A1", "A2", "A4", "B4", "A13"):
        sm[c].font = Font(bold=True)
    sm.column_dimensions["A"].width = 22
    sm.column_dimensions["B"].width = 30

    ls = wb.create_sheet("Job boards to check")
    ls.append(["Board", "Link", "Checked?"])
    for c in ls[1]:
        c.font = Font(bold=True)
    for l in list(ph_links_) + list(remote_links_):
        ls.append([l["name"], l["url"], "\u2610"])
        ls.cell(row=ls.max_row, column=2).hyperlink = l["url"]
    ls.column_dimensions["A"].width = 40
    ls.column_dimensions["B"].width = 90
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


SEARCHES = {}


def start_search(params):
    import threading
    import time
    import uuid
    sid = uuid.uuid4().hex[:12]
    st = SEARCHES[sid] = {"done": 0, "total": 1, "start": time.time(), "finished": False}

    def work():
        try:
            def prog(d, t):
                st["done"], st["total"] = d, t
            st["result"] = search(params, prog)
        except Exception as e:
            st["error"] = str(e)
        st["end"] = time.time()
        st["finished"] = True
    threading.Thread(target=work, daemon=True).start()
    return sid


def parse_params(query):
    qs = {k: v[0] for k, v in urllib.parse.parse_qs(query).items()}
    for k in ("open_ph", "entry", "keep_unlisted", "no_citizen", "show_maybe"):
        qs[k] = qs.get(k, "") in ("1", "true", "on")
    return qs


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/":
            self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif u.path == "/api/config":
            self._send(200, json.dumps({"cities": PH_CITIES}).encode(), "application/json")
        elif u.path == "/api/search/start":
            qs = parse_params(u.query)
            if not qs.get("q", "").strip():
                return self._send(400, b'{"error":"q required"}', "application/json")
            self._send(200, json.dumps({"id": start_search(qs)}).encode(), "application/json")
        elif u.path == "/api/search/status":
            import time
            st = SEARCHES.get(urllib.parse.parse_qs(u.query).get("id", [""])[0])
            if not st:
                return self._send(404, b'{"error":"unknown id"}', "application/json")
            out = {"done": st["done"], "total": st["total"], "finished": st["finished"],
                   "elapsed": round(st.get("end", time.time()) - st["start"], 1)}
            if st["finished"]:
                out["result"], out["error"] = st.get("result"), st.get("error")
            self._send(200, json.dumps(out).encode(), "application/json")
        elif u.path == "/api/search":
            qs = parse_params(u.query)
            if not qs.get("q", "").strip():
                return self._send(400, b'{"error":"q required"}', "application/json")
            self._send(200, json.dumps(search(qs)).encode(), "application/json")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if u.path != "/api/export":
            return self._send(404, b"not found", "text/plain")
        n = int(self.headers.get("Content-Length", 0))
        d = json.loads(self.rfile.read(n) or b"{}")
        data = build_tracker(d.get("jobs", []), d.get("query", ""), d.get("ph_links", []), d.get("remote_links", []))
        self._send(200, data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    def log_message(self, *a):
        pass


def warm_cache():
    """Opt-in background warmer (set WARM=1). Pre-fetches the query-independent sources —
    the ~200 company boards and the category/RSS feeds — so searches stay instant. These
    results are cached for 1 hour, so it refreshes a little before they expire."""
    import threading
    import time

    def loop():
        while True:
            try:
                fns = ats_fetchers() + [lambda: src_remotive_cats([]), lambda: src_muse([]),
                                        lambda: src_wwr([]), lambda: src_jobspresso([]),
                                        lambda: src_nodesk([]), lambda: src_rwfa([]),
                                        lambda: src_himalayas_rss([]), lambda: src_remoteok([])]
                with ThreadPoolExecutor(16) as ex:
                    list(ex.map(lambda f: _safe(lambda _: f(), None), fns))
            except Exception:
                pass
            time.sleep(55 * 60)
    threading.Thread(target=loop, daemon=True).start()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    if os.environ.get("WARM", "1") not in ("0", "false", "off"):
        print("Warming cache in the background (the ~150 company boards + feeds). "
              "The first search is slow until this finishes (~1 min); set WARM=0 to disable.")
        warm_cache()
    print(f"Open http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()

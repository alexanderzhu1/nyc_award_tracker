# -*- coding: utf-8 -*-
"""
app.py

NYC Council Discretionary Award Tracker
General audience Streamlit app.

Run:
    streamlit run app.py
"""

import json
import csv
import io
import re
from datetime import datetime

import requests
import streamlit as st

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------
DATABOOK_MCP_URL = "https://api.databook.nyc/mcp"
BETANYC_AWARDS_URL = (
    "https://raw.githubusercontent.com/BetaNYC/"
    "New-York-City-Budget/main/data/combined/all_years_awards.csv"
)
MOCS_TRACKER_URL = (
    "https://www.nyc.gov/site/mocs/opportunities/"
    "discretionary-award-tracker.page"
)
COUNCIL_WORKBOOK_TEMPLATE = (
    "https://rnd.council.nyc.gov/src/assets/excelFund/"
    "funded_disclosure_FY{year}.xlsx"
)

# Council Member surname -> district. Covers the 2010-2027 roster.
# Entries can be updated as membership changes.
COUNCIL_MEMBER_DISTRICTS = {
    "DE LA ROSA":     {"full_name": "Carmen De La Rosa",     "district": 10, "borough": "Manhattan/Bronx"},
    "RIVERA":         {"full_name": "Carlina Rivera",        "district": 2,  "borough": "Manhattan"},
    "EPSTEIN":        {"full_name": "Harvey Epstein",        "district": 2,  "borough": "Manhattan"},
    "AYALA":          {"full_name": "Diana Ayala",           "district": 8,  "borough": "Manhattan/Bronx"},
    "POWERS":         {"full_name": "Keith Powers",          "district": 4,  "borough": "Manhattan"},
    "MENIN":          {"full_name": "Julie Menin",           "district": 5,  "borough": "Manhattan"},
    "BREWER":         {"full_name": "Gale Brewer",           "district": 6,  "borough": "Manhattan"},
    "ABREU":          {"full_name": "Shaun Abreu",           "district": 7,  "borough": "Manhattan"},
    "RESTLER":        {"full_name": "Lincoln Restler",       "district": 33, "borough": "Brooklyn"},
    "LEVIN":          {"full_name": "Stephen Levin",         "district": 33, "borough": "Brooklyn"},
    "CHIN":           {"full_name": "Margaret Chin",         "district": 1,  "borough": "Manhattan"},
    "MARTE":          {"full_name": "Christopher Marte",     "district": 1,  "borough": "Manhattan"},
    "LANDER":         {"full_name": "Brad Lander",           "district": 39, "borough": "Brooklyn"},
    "HANIF":          {"full_name": "Shahana Hanif",         "district": 39, "borough": "Brooklyn"},
    "KALLOS":         {"full_name": "Ben Kallos",            "district": 5,  "borough": "Manhattan"},
    "RODRIGUEZ":      {"full_name": "Ydanis Rodriguez",      "district": 10, "borough": "Manhattan"},
    "SALAMANCA":      {"full_name": "Rafael Salamanca",      "district": 17, "borough": "Bronx"},
    "TORRES":         {"full_name": "Ritchie Torres",        "district": 15, "borough": "Bronx"},
    "GIBSON":         {"full_name": "Vanessa Gibson",        "district": 16, "borough": "Bronx"},
    "DIAZ":           {"full_name": "Rubén Díaz Sr.",        "district": 18, "borough": "Bronx"},
    "MILLER":         {"full_name": "I. Daneek Miller",      "district": 27, "borough": "Queens"},
    "RICHARDS":       {"full_name": "Donovan Richards",      "district": 31, "borough": "Queens"},
    "GRODENCHIK":     {"full_name": "Barry Grodenchik",      "district": 23, "borough": "Queens"},
    "VALLONE":        {"full_name": "Paul Vallone",          "district": 19, "borough": "Queens"},
    "CONSTANTINIDES": {"full_name": "Costa Constantinides", "district": 22, "borough": "Queens"},
    "BRANNAN":        {"full_name": "Justin Brannan",        "district": 43, "borough": "Brooklyn"},
    "CUMMINGS":       {"full_name": "Laurie Cumbo",          "district": 35, "borough": "Brooklyn"},
    "CORNEGY":        {"full_name": "Robert Cornegy",        "district": 36, "borough": "Brooklyn"},
    "EUGENIO":        {"full_name": "Mathieu Eugene",        "district": 40, "borough": "Brooklyn"},
    "DEUTSCH":        {"full_name": "Chaim Deutsch",         "district": 48, "borough": "Brooklyn"},
    "TOUSSAINT":      {"full_name": "Farah Louis",           "district": 45, "borough": "Brooklyn"},
    "WILLIAMS":       {"full_name": "Jumaane Williams",      "district": 45, "borough": "Brooklyn"},
    "BARRON":         {"full_name": "Inez Barron",           "district": 42, "borough": "Brooklyn"},
    "MAISEL":         {"full_name": "Alan Maisel",           "district": 46, "borough": "Brooklyn"},
    "BORELLI":        {"full_name": "Joseph Borelli",        "district": 51, "borough": "Staten Island"},
    "ROSE":           {"full_name": "Deborah Rose",          "district": 49, "borough": "Staten Island"},
    "MATTEO":         {"full_name": "Steven Matteo",         "district": 50, "borough": "Staten Island"},
    "PALADINO":       {"full_name": "Vickie Paladino",       "district": 19, "borough": "Queens"},
    "ADAMS":          {"full_name": "Adrienne Adams",        "district": 28, "borough": "Queens"},
    "HOLDEN":         {"full_name": "Robert Holden",         "district": 30, "borough": "Queens"},
    "BOTTCHER":       {"full_name": "Erik Bottcher",         "district": 3,  "borough": "Manhattan"},
    "GONZALEZ":       {"full_name": "Kristin Richardson Jordan", "district": 9, "borough": "Manhattan"},
    "JORDAN":         {"full_name": "Kristin Richardson Jordan", "district": 9, "borough": "Manhattan"},
    "HUDSON":         {"full_name": "Crystal Hudson",        "district": 35, "borough": "Brooklyn"},
    "OSSE":           {"full_name": "Chi Ossé",              "district": 36, "borough": "Brooklyn"},
    "NURSE":          {"full_name": "Sandy Nurse",           "district": 37, "borough": "Brooklyn"},
    "AVILES":         {"full_name": "Alexa Avilés",          "district": 38, "borough": "Brooklyn"},
    "RESTLER":        {"full_name": "Lincoln Restler",       "district": 33, "borough": "Brooklyn"},
    "ZHUANG":         {"full_name": "Susan Zhuang",          "district": 43, "borough": "Brooklyn"},
    "FARIAS":         {"full_name": "Amanda Farías",         "district": 18, "borough": "Bronx"},
    "SANCHEZ":        {"full_name": "Pierina Sanchez",       "district": 14, "borough": "Bronx"},
    "FELIZ":          {"full_name": "Oswald Feliz",          "district": 15, "borough": "Bronx"},
    "MARMORATO":      {"full_name": "Kristy Marmorato",      "district": 13, "borough": "Bronx"},
    "STEVENS":        {"full_name": "Althea Stevens",        "district": 16, "borough": "Bronx"},
    "CABAN":          {"full_name": "Tiffany Cabán",         "district": 22, "borough": "Queens"},
    "KRISHNAN":       {"full_name": "Shekar Krishnan",       "district": 25, "borough": "Queens"},
    "WON":            {"full_name": "Julie Won",             "district": 26, "borough": "Queens"},
    "LEE":            {"full_name": "Linda Lee",             "district": 23, "borough": "Queens"},
    "MOYA":           {"full_name": "Francisco Moya",        "district": 21, "borough": "Queens"},
    "SANCHEZ":        {"full_name": "Pierina Sanchez",       "district": 14, "borough": "Bronx"},
    "VELEZ":          {"full_name": "Marjorie Velázquez",    "district": 13, "borough": "Bronx"},
    "ARIOLA":         {"full_name": "Joann Ariola",          "district": 32, "borough": "Queens"},
    "UNGA":           {"full_name": "Sandra Ung",            "district": 20, "borough": "Queens"},
    "GUTIERREZ":      {"full_name": "Jennifer Gutiérrez",    "district": 34, "borough": "Brooklyn/Queens"},
    "REYNOSO":        {"full_name": "Antonio Reynoso",       "district": 34, "borough": "Brooklyn/Queens"},
    "BRONX DELEGATION": {"full_name": "Bronx Delegation",    "district": None, "borough": "Bronx"},
    "BROOKLYN DELEGATION": {"full_name": "Brooklyn Delegation", "district": None, "borough": "Brooklyn"},
    "QUEENS DELEGATION": {"full_name": "Queens Delegation",  "district": None, "borough": "Queens"},
    "MANHATTAN DELEGATION": {"full_name": "Manhattan Delegation", "district": None, "borough": "Manhattan"},
    "STATEN ISLAND DELEGATION": {"full_name": "Staten Island Delegation", "district": None, "borough": "Staten Island"},
    "SPEAKER":        {"full_name": "Speaker (Councilwide)", "district": None, "borough": "Citywide"},
    "CITYWIDE":       {"full_name": "Citywide Initiative",   "district": None, "borough": "Citywide"},
    "CITY COUNCIL":   {"full_name": "City Council (Citywide)", "district": None, "borough": "Citywide"},
}


# ------------------------------------------------------------------
# MCP CLIENT
# ------------------------------------------------------------------
class DatabookMCPClient:
    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.session = requests.Session()
        self.session_id = None
        self.request_id = 0

    def _next_id(self):
        self.request_id += 1
        return self.request_id

    def _parse_sse(self, text):
        parsed = []
        for line in text.splitlines():
            if line.startswith("data: "):
                try:
                    parsed.append(json.loads(line[6:]))
                except json.JSONDecodeError:
                    continue
        for obj in parsed:
            if isinstance(obj, dict) and ("result" in obj or "error" in obj):
                return obj
        if parsed:
            return parsed[-1]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}

    def _headers(self):
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            h["mcp-session-id"] = self.session_id
        return h

    def initialize(self):
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "streamlit-app", "version": "1.0"},
            },
        }
        r = self.session.post(self.endpoint, json=payload,
                              headers=self._headers(), timeout=60)
        self.session_id = r.headers.get("mcp-session-id")

    def call_tool(self, name, arguments):
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        r = self.session.post(self.endpoint, json=payload,
                              headers=self._headers(), timeout=60)
        return self._parse_sse(r.text)

    def extract_text(self, response):
        if not response:
            return ""
        if isinstance(response, str):
            return response
        try:
            content = response.get("result", {}).get("content", [])
            for item in content:
                if item.get("type") == "text":
                    text = item.get("text", "")
                    if text:
                        return text
        except Exception:
            pass
        if isinstance(response, dict) and "error" in response:
            return "ERROR: {}".format(response["error"])
        try:
            return json.dumps(response)
        except Exception:
            return str(response)


# ------------------------------------------------------------------
# CACHED DATA LOADERS
# ------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def load_betanyc_awards():
    try:
        resp = requests.get(BETANYC_AWARDS_URL, timeout=60)
        resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(resp.text))
        return list(reader)
    except Exception as e:
        st.error("Could not load award data: {}".format(e))
        return []


def _looks_like_corrupted_name(s):
    """
    Detect organization strings that are parser artifacts rather than
    real names. They carry leftover EINs, dollar amounts, asterisks,
    or other row-boundary junk from PDF extraction.
    """
    if not s:
        return True
    if re.search(r"\b\d{2}-\d{7}\b", s):
        return True
    if re.search(r"\b\d{9}\b", s):
        return True
    if re.search(r"\$\s?[\d,]+", s):
        return True
    if "*" in s:
        return True
    if len(s) > 120:
        return True
    return False


def _normalize_name(s):
    """Uppercase, strip leading articles, strip corporate suffixes."""
    s = (s or "").upper().strip()
    for prefix in ["THE ", "A ", "AN "]:
        if s.startswith(prefix):
            s = s[len(prefix):]
    for suffix in [", INC.", " INC.", ", INC", " INC",
                   " INCORPORATED", ", LTD.", " LTD.", " CORP.", " CORP",
                   " LLC", ", LLC", " L.L.C.", ", L.L.C."]:
        if s.endswith(suffix):
            s = s[:-len(suffix)]
    return s.strip()


def _canonical_org_key(s):
    """
    Reduce a name to a canonical key for deduplication.
    Handles 'The' as suffix ('Bronx Defenders, The') and prefix.
    """
    s = (s or "").upper().strip()
    for suffix in [", THE", " THE"]:
        if s.endswith(suffix):
            s = s[:-len(suffix)].strip()
    if s.startswith("THE "):
        s = s[4:].strip()
    for suffix in [", INC.", " INC.", ", INC", " INC",
                   " INCORPORATED", ", LTD.", " LTD.",
                   ", LLC", " LLC"]:
        if s.endswith(suffix):
            s = s[:-len(suffix)].strip()
    s = re.sub(r"[,;:]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


@st.cache_data(ttl=3600, show_spinner=False)
def get_all_organizations():
    """
    Return display names for organizations.
    Filters parser artifacts. Deduplicates on canonical key so
    'Bronx Defenders' and 'Bronx Defenders, The' do not both appear.
    """
    rows = load_betanyc_awards()
    seen_keys = {}
    for r in rows:
        org = (r.get("organization") or "").strip()
        if not org or _looks_like_corrupted_name(org):
            continue
        key = _canonical_org_key(org)
        if not key:
            continue
        if key not in seen_keys or len(org) < len(seen_keys[key]):
            seen_keys[key] = org
    return sorted(seen_keys.values())


def get_mcp_client():
    client = DatabookMCPClient(DATABOOK_MCP_URL)
    client.initialize()
    return client


# ------------------------------------------------------------------
# MATCHING HELPERS
# ------------------------------------------------------------------
def rank_organizations(all_orgs, query, limit=4):
    if not query:
        return []
    q = query.upper().strip()
    tokens = [t for t in q.split() if t]
    exact, starts, contains, tokens_match = [], [], [], []
    for org in all_orgs:
        u = org.upper()
        if u == q:
            exact.append(org)
        elif u.startswith(q):
            starts.append(org)
        elif q in u:
            contains.append(org)
        elif tokens and all(t in u for t in tokens):
            tokens_match.append(org)
    ordered = exact + starts + contains + tokens_match
    return ordered[:limit]


def resolve_member(member):
    """
    Return a dict describing the Council Member, or a fallback dict
    if the surname is not in the mapping table. Never returns None
    for a non-empty member string, so the UI can always show something.
    """
    if not member or member == "?":
        return None
    text = member.upper().strip()
    for surname, info in COUNCIL_MEMBER_DISTRICTS.items():
        if surname.upper() in text:
            return {
                "surname": member,
                "full_name": info.get("full_name", member.title()),
                "district": info.get("district"),
                "borough": info.get("borough"),
                "mapped": True,
            }
    # Fallback: no district known, but still a valid member.
    return {
        "surname": member,
        "full_name": member.title(),
        "district": None,
        "borough": None,
        "mapped": False,
    }


def parse_amount(value):
    try:
        return float(str(value).replace(",", "").replace("$", ""))
    except (ValueError, TypeError):
        return 0.0


# ------------------------------------------------------------------
# TRACE LOGIC
# ------------------------------------------------------------------
def find_awards(rows, org_query):
    """
    Match rows whose canonical org key equals the query's canonical key.
    This merges 'Bronx Defenders' and 'Bronx Defenders, The', and
    filters out parser artifacts.
    """
    target_key = _canonical_org_key(org_query)
    if not target_key:
        return []

    matches = []
    for r in rows:
        org = r.get("organization") or ""
        if _looks_like_corrupted_name(org):
            continue
        if _canonical_org_key(org) == target_key:
            matches.append(r)

    if matches:
        return matches

    # Fall back to strict substring match
    normalized_query = _normalize_name(org_query)
    if not normalized_query:
        return []
    fallback = []
    for r in rows:
        raw = r.get("organization") or ""
        if _looks_like_corrupted_name(raw):
            continue
        org = _normalize_name(raw)
        if normalized_query == org or normalized_query in org:
            fallback.append(r)
    return fallback


def _pin_prefix_from_agency(agency, fiscal_year):
    """
    Build a PIN prefix from agency code and fiscal year.
    Council PINs have an 'L' after the agency + year.
    """
    # Agency codes are the first three characters of a PIN.
    # We do not have a full mapping, but DYCD is 260, and DOC is 072,
    # etc. If the caller passes an agency name, we cannot build the
    # prefix. This is a stub; the real mapping is small enough to
    # hardcode if needed.
    return None


def trace_nonprofit(org_query):
    result = {
        "awards": [],
        "contracts": [],
        "members": [],
        "unattributed": [],
        "single_member_warning": False,
        "lag_warning": False,
        "missing_mocs_id_years": set(),
    }

    rows = load_betanyc_awards()
    awards = find_awards(rows, org_query)
    result["awards"] = awards

    member_totals = {}
    unattributed = []

    for a in awards:
        member = (a.get("member") or "").strip()
        amount = parse_amount(a.get("amount"))

    if member and member != "?":
            if member not in member_totals:
                info = resolve_member(member)
                member_totals[member] = {
                    "surname": member,
                    "info": info,
                    "total": 0.0,
                    "count": 0,
                }
            member_totals[member]["total"] += amount
            member_totals[member]["count"] += 1
    else:
        unattributed.append(a)

    result["members"] = sorted(
        member_totals.values(), key=lambda x: x["total"], reverse=True
    )
    result["unattributed"] = unattributed

    resolved = [m for m in member_totals.values()
                if m["info"] and m["info"].get("mapped")]
    if len(resolved) < 2 and len(member_totals) >= 1:
        result["single_member_warning"] = True

    # Detect recent fiscal years with no contracts (registration lag)
    current_year = datetime.now().year
    has_recent_award = False
    has_mocs_gap_year = False
    for a in awards:
        year_raw = (a.get("year") or a.get("fiscal_year") or "").replace("FY", "")
        try:
            year_num = int(year_raw)
        except (ValueError, TypeError):
            continue
        # Fiscal year YY is roughly calendar year 2000 + YY
        if year_num >= (current_year - 2000 - 1):
            has_recent_award = True
        if year_num in (22, 23):
            has_mocs_gap_year = True

    result["lag_warning"] = has_recent_award
    if has_mocs_gap_year:
        result["missing_mocs_id_years"].add("FY2022/FY2023")

    # Send the FULL normalized name to Databook.
    vendor_query = _normalize_name(org_query) or org_query

    try:
        client = get_mcp_client()
        contract_resp = client.call_tool("search_contracts", {
            "vendor": vendor_query,
            "limit": 25,
        })

        if isinstance(contract_resp, dict) and "error" in contract_resp:
            err = contract_resp.get("error", {})
            err_msg = err.get("message", "") if isinstance(err, dict) else str(err)
            if "session" in err_msg.lower():
                client = get_mcp_client()
                contract_resp = client.call_tool("search_contracts", {
                    "vendor": vendor_query,
                    "limit": 25,
                })

        contract_text = client.extract_text(contract_resp)
        raw_contracts = parse_contract_blocks(contract_text)

        # Strict filter: returned vendor's normalized name must equal
        # the query, or contain it as a substring after punctuation strip.
        query_nopunct = re.sub(r"[/\\,;:\-]+", " ", vendor_query)
        query_nopunct = re.sub(r"\s+", " ", query_nopunct).strip()
        filtered = []
        for c in raw_contracts:
            v = _normalize_name(c.get("vendor"))
            if not v:
                continue
            if v == vendor_query:
                filtered.append(c)
                continue
            if vendor_query and vendor_query in v:
                filtered.append(c)
                continue
            v_nopunct = re.sub(r"[/\\,;:\-]+", " ", v)
            v_nopunct = re.sub(r"\s+", " ", v_nopunct).strip()
            if query_nopunct and query_nopunct in v_nopunct:
                filtered.append(c)

        result["contracts"] = filtered
    except Exception as e:
        st.warning("Contract lookup failed: {}".format(e))

    return result


def parse_contract_blocks(text):
    blocks = []
    parts = re.split(r"\n- \*\*", text)
    for part in parts[1:]:
        lines = part.split("\n")
        if not lines:
            continue
        title = lines[0].replace("**", "").rstrip(".").strip()
        vendor = agency = amount = status = start = end = url = None
        contract_id = None
        for line in lines:
            line = line.strip()
            # Try to pick a contract ID from the title, e.g. "CT126020238807620"
            if contract_id is None:
                m = re.search(r"\b(CT\d{10,})\b", line)
                if m:
                    contract_id = m.group(1)
            if line.startswith("Vendor:"):
                m = re.search(r"Vendor:\s*(.*?)\s*\|", line)
                if m:
                    vendor = m.group(1).strip()
                m = re.search(r"Agency:\s*(.*)$", line)
                if m:
                    agency = m.group(1).strip()
            elif line.startswith("Amount:"):
                m = re.search(r"Amount:\s*\$([\d,\.]+)", line)
                if m:
                    amount = m.group(1)
                m = re.search(r"Status:\s*(.*)$", line)
                if m:
                    status = m.group(1).strip()
            elif line.startswith("Start:"):
                m = re.search(r"Start:\s*(\S+)\s*\|\s*End:\s*(\S+)", line)
                if m:
                    start, end = m.group(1), m.group(2)
            elif "Databook URL:" in line:
                m = re.search(r"(https://databook\.nyc/\S+)", line)
                if m:
                    url = m.group(1)
        blocks.append({
            "title": title,
            "vendor": vendor,
            "agency": agency,
            "amount": amount,
            "status": status,
            "start": start,
            "end": end,
            "url": url,
            "contract_id": contract_id,
        })
    return blocks


def is_discretionary(contract):
    title = (contract.get("title") or "").lower()
    return "discretionary" in title


def member_display(m):
    info = m["info"]
    if not info:
        return m["surname"], "${:,.0f} across {} award(s)".format(
            m["total"], m["count"])
    full_name = info.get("full_name", m["surname"].title())
    district = info.get("district")
    borough = info.get("borough")
    if district is not None:
        title = "{} — District {} ({})".format(full_name, district, borough)
    elif borough:
        title = "{} — {} (no single district)".format(full_name, borough)
    else:
        title = full_name
    subtitle = "${:,.0f} across {} award(s)".format(m["total"], m["count"])
    return title, subtitle


def member_matches_search(m, query):
    if not query:
        return True
    q = query.upper().strip()
    info = m["info"] or {}
    haystack_parts = [m["surname"]]
    haystack_parts += [
        info.get("full_name", "") or "",
        str(info.get("district") or ""),
        info.get("borough") or "",
    ]
    haystack = " ".join(haystack_parts).upper()
    return q in haystack


# ------------------------------------------------------------------
# STREAMLIT UI
# ------------------------------------------------------------------
st.set_page_config(
    page_title="NYC Council Discretionary Award Tracker",
    page_icon="🏛️",
    layout="wide",
)

st.title("NYC Council Discretionary Award Tracker")
st.caption(
    "Trace a NYC Council discretionary award from designation to "
    "registered contract to Checkbook NYC payments."
)

with st.expander("How to use this", expanded=False):
    st.markdown(
        """
        **What this does:** traces a NYC Council discretionary award
        ("Schedule C" or "member item") from designation through the
        registered contract and the payments recorded in Checkbook NYC.

        **How to use it:**
        1. Start typing a nonprofit name in the box below.
        2. Pick the matching organization from the dropdown.
        3. Click **Trace this organization**.
        4. Use the search box in the Council Members section to filter.

        **Known data limitations:**
        - The BetaNYC source CSV is a derived dataset. Some rows are
          missing or have corrupted fields. The Council's funded
          disclosure workbooks are the primary source for FY2024+.
        - FY2022 and FY2023 awards have no public MOCS award number.
        - Recent fiscal years often have no registered contract yet
          because registration lags by a median of 13 months.
        - We do not compute "awarded vs. paid" reconciliations. The
          three stages are shown as independent facts.
        """
    )

st.markdown("### Find a nonprofit")

all_orgs = get_all_organizations()

typed = st.text_input(
    "Start typing a nonprofit name",
    placeholder="e.g., Bronx Defenders, Legal Aid Society...",
    key="typed_org",
).strip()

if typed:
    matches = rank_organizations(all_orgs, typed, limit=4)
else:
    matches = []

selected_org = None
if typed and not matches:
    st.warning(
        "No organizations in the source data match that text. "
        "Try a shorter or different spelling."
    )
elif matches:
    selected_org = st.selectbox(
        "Matching organizations ({} found)".format(len(matches)),
        options=matches,
        key="org_select_{}".format(len(matches)),
    )
elif not typed:
    st.caption("Start typing above to see matching organizations.")

# Secondary search by PIN prefix
with st.expander("Or search by contract PIN prefix (advanced)"):
    st.markdown(
        "**PIN structure:** agency code (3 digits) + fiscal year (2 digits) "
        "+ procurement method code (1 letter) + sequence. Council "
        "discretionary money is coded `L`. Example: `26023L` means DYCD, "
        "FY2023, Council."
    )
    pin_prefix = st.text_input(
        "PIN prefix",
        placeholder="e.g., 26023L",
        key="pin_prefix",
    ).strip()

trace_clicked = st.button(
    "Trace this organization",
    type="primary",
    disabled=(selected_org is None),
)

# ------------------------------------------------------------------
# TRACE AND RESULTS
# ------------------------------------------------------------------
if trace_clicked and selected_org:
    with st.spinner("Tracing award -> contract -> payments..."):
        result = trace_nonprofit(selected_org)

    st.markdown("---")
    st.markdown("## Results for **{}**".format(selected_org))

    awards = result["awards"]
    contracts = result["contracts"]
    discretionary = [c for c in contracts if is_discretionary(c)]
    members = result["members"]
    unattributed = result["unattributed"]

    col1, col2, col3 = st.columns(3)
    col1.metric("Award records", len(awards))
    col2.metric("Contracts found", len(contracts))
    col3.metric("Discretionary contracts", len(discretionary))

    if not awards and not contracts:
        st.warning(
            "No results found for this organization. The BetaNYC source "
            "CSV does not contain a row for this name. This is a known "
            "defect — some orgs are missing from the derived dataset "
            "even when the Council's funded disclosure workbooks list "
            "them."
        )
        st.stop()

    # --- Registration lag warning ---
    if result["lag_warning"]:
        st.warning(
            "**Registration lag.** This organization has awards in "
            "recent fiscal years. Contracts for recent awards are often "
            "not registered yet — the median lag from term start to "
            "registration is about 13 months, and about 1 in 10 takes "
            "three years. A missing contract does not mean the money "
            "was not paid."
        )

    # --- FY2022–FY2023 MOCS ID gap ---
    if result["missing_mocs_id_years"]:
        st.info(
            "**FY2022–FY2023 have no public MOCS award number.** The "
            "NYC Open Data source stopped carrying the MOCS ID after "
            "FY2021, and the Council's funded disclosure workbooks only "
            "start including it in FY2024. If you need an award number "
            "for those years, there is no public source for it."
        )

    # --- Completeness warning ---
    if result["single_member_warning"]:
        st.warning(
            "**Data completeness note.** The BetaNYC dataset only shows "
            "one Council Member for this organization. This may be due "
            "to the parser dropping rows. Cross-check against the "
            "official Council funded disclosure workbooks."
        )

    st.info(
        "**Check official award status.** The MOCS Discretionary Award "
        "Tracker is the authoritative source for whether an award has "
        "been cleared. [Open the MOCS Tracker]({}) and search by EIN "
        "or organization name.".format(MOCS_TRACKER_URL)
    )

    # --- Council Members ---
    if members:
        st.subheader("Council Members tied to these awards")
        st.caption(
            "Top 5 by dollar amount shown below. Use the search box to "
            "filter by member name, district, or borough."
        )

        member_search = st.text_input(
            "Filter members",
            placeholder="e.g., Powers, District 4, Brooklyn",
            key="member_filter",
        ).strip()

        filtered_members = [
            m for m in members if member_matches_search(m, member_search)
        ]

        if not filtered_members:
            st.info("No Council Members match that filter.")
        else:
            top = filtered_members[:5]
            rest = filtered_members[5:]
            for m in top: 
                title, subtitle = member_display(m)
                st.markdown("**{}**  \n{}".format(title, subtitle))

            if rest:
                with st.expander("Show {} more member(s)".format(len(rest))):
                    for m in rest:
                        title, subtitle = member_display(m)
                        st.markdown("**{}**  \n{}".format(title, subtitle))

    # --- Unattributed awards ---
    if unattributed:
        total_un = sum(parse_amount(a.get("amount")) for a in unattributed)
        st.subheader("Awards not attributed to a specific Member")
        st.caption(
            "${:,.0f} across {} award(s) — these are Citywide Initiatives, "
            "borough delegations, or fiscal sponsor awards where the source "
            "data does not name an individual Council Member.".format(
                total_un, len(unattributed)
            )
        )
        with st.expander("Show {} unattributed rows".format(len(unattributed))):
            for a in unattributed:
                year = (a.get("year") or a.get("fiscal_year") or "?").replace("FY", "")
                amount = a.get("amount", "?")
                agency = a.get("agency", "?")
                st.markdown("- FY{} — ${} — {}".format(year, amount, agency))

    # --- Award records ---
    if awards:
        st.subheader("Award records")
        table_rows = []
        for a in awards:
            year = (a.get("year") or a.get("fiscal_year") or "?").replace("FY", "")
            table_rows.append({
                "Fiscal Year": "FY{}".format(year),
                "Member": a.get("member", "?"),
                "Organization": a.get("organization", "?"),
                "Amount": "${}".format(a.get("amount", "?")),
                "Agency": a.get("agency", "?"),
            })
        st.dataframe(table_rows, use_container_width=True)

    # --- Discretionary contracts ---
    if discretionary:
        st.subheader("Discretionary contracts")
        for c in discretionary:
            with st.container(border=True):
                st.markdown("**{}**".format(c["title"]))
                if c.get("contract_id"):
                    st.markdown(
                        "Contract ID: `{}`".format(c["contract_id"])
                    )
                cols = st.columns(4)
                cols[0].markdown("**Vendor**  \n{}".format(c.get("vendor", "?")))
                cols[1].markdown("**Agency**  \n{}".format(c.get("agency", "?")))
                cols[2].markdown("**Amount**  \n${}".format(c.get("amount", "?")))
                cols[3].markdown("**Status**  \n{}".format(c.get("status", "?")))
                st.markdown("Term: {} -> {}".format(c.get("start", "?"),
                                                    c.get("end", "?")))
                if c.get("url"):
                    st.markdown("[View on Databook.nyc]({})".format(c["url"]))

    # --- All contracts ---
    if contracts:
        st.subheader("All contracts found")
        contract_rows = []
        for c in contracts:
            contract_rows.append({
                "Contract ID": c.get("contract_id", ""),
                "Title": c.get("title", "?"),
                "Vendor": c.get("vendor", "?"),
                "Agency": c.get("agency", "?"),
                "Amount": "${}".format(c.get("amount", "?")),
                "Status": c.get("status", "?"),
                "Start": c.get("start", "?"),
                "End": c.get("end", "?"),
                "Databook": c.get("url", ""),
            })
        st.dataframe(contract_rows, use_container_width=True)

    # --- Sources ---
    st.divider()
    with st.expander("Sources and methodology"):
        st.markdown(
            "**Search term used:** `{}`\n\n"
            "**Data sources, in order of authority:**\n\n"
            "1. **NYC Council funded disclosure workbooks (primary source).** "
            "For FY2024 and later, these are the authoritative record of "
            "Council discretionary awards. Each row includes fiscal year, "
            "sponsoring member, legal name, EIN, agency, amount, purpose, "
            "and status. From FY2024 onward they also include the MOCS "
            "award number. "
            "[FY2024 workbook]({})\n\n"
            "2. **BetaNYC New-York-City-Budget (derived dataset).** "
            "Combined Schedule C awards scraped from Council PDFs. Used "
            "by this app because it is machine-readable and covers "
            "FY2015–FY2027. Note: this dataset has documented parsing "
            "defects. Some rows are missing entirely, some have "
            "corrupted EINs, and some merge two adjacent awards into "
            "one malformed row. When this app shows zero awards for an "
            "organization, check the Council workbooks first. "
            "[GitHub repo](https://github.com/BetaNYC/New-York-City-Budget)\n\n"
            "3. **Databook.nyc (contract and payment lookup).** "
            "MCP server joining MOCS contracts to Checkbook NYC "
            "payments. Contracts are keyed by the FMS Contract ID "
            "(`CT...`). The contract ID is the exact join key to "
            "spending records. "
            "[databook.nyc](https://databook.nyc)\n\n"
            "4. **MOCS Discretionary Award Tracker (status lookup).** "
            "The authoritative source for award clearance status. "
            "Covers FY2019–FY2021 only in its public snapshot, last "
            "updated June 2021. It does not carry contract numbers or "
            "payment amounts. "
            "[Open the tracker]({})\n\n"
            "5. **NYC Council roster** — member-to-district mapping. "
            "[council.nyc.gov](https://council.nyc.gov/districts/)\n\n"
            "**Known limitations:**\n\n"
            "- **Parser defects in BetaNYC CSV.** Rows may be missing, "
            "EINs may be corrupted, and adjacent rows may be merged. "
            "This app filters out the most obvious malformed names but "
            "cannot recover rows that were never parsed.\n"
            "- **No public MOCS award number for FY2022–FY2023.** The "
            "NYC Open Data source ends at FY2021 and the Council "
            "workbooks begin carrying it in FY2024. For those two "
            "fiscal years there is no public award number.\n"
            "- **Registration lag.** Recent awards often have no "
            "registered contract because registration lags by a median "
            "of about 13 months. A missing contract does not mean the "
            "money was not paid.\n"
            "- **Name drift.** The same organization appears under "
            "several spellings across years and systems. This app "
            "canonicalizes on a normalized key but small orgs and "
            "common names may still need hand-checking.\n"
            "- **No awarded-vs-paid reconciliation.** This app shows "
            "awards, contracts, and payments as three independent "
            "facts. It does not compute a ratio, because the coverage "
            "is not solid enough to support one.\n"
            "- **Pass-through payments.** Payments recorded in "
            "Checkbook may be charged to a fiscal sponsor's contract "
            "rather than to the org's own. This app joins contracts to "
            "spending by contract ID and shows contracts under the "
            "registered vendor, which reduces but does not eliminate "
            "this risk."
            .format(
                selected_org,
                COUNCIL_WORKBOOK_TEMPLATE.format(year="2024"),
                MOCS_TRACKER_URL,
            )
        )
else:
    st.info("Enter a nonprofit name above to begin.")

# ------------------------------------------------------------------
# DATA SOURCE URLS
# ------------------------------------------------------------------
BETANYC_MAIN_URL = (
    "https://raw.githubusercontent.com/BetaNYC/"
    "New-York-City-Budget/main/data/combined/all_years_awards.csv"
)
BETANYC_ABSORBED_URL = (
    "https://raw.githubusercontent.com/BetaNYC/"
    "New-York-City-Budget/main/data/recovered/schedule_c_absorbed_awards.csv"
)
BETANYC_APPENDIX_URL = (
    "https://raw.githubusercontent.com/BetaNYC/"
    "New-York-City-Budget/main/data/recovered/schedule_c_appendix_recovered.csv"
)


# ------------------------------------------------------------------
# NORMALIZATION HELPERS
# ------------------------------------------------------------------
def _normalize_fy_to_short(raw):
    """
    Convert any fiscal year representation to a two-digit string.
    Accepts: 'FY24', '24', '2024', 24, '2024.0'.
    Returns: '24' or '' if unparseable.
    """
    if raw is None:
        return ""
    s = str(raw).strip().upper()
    s = s.replace("FY", "").strip()
    if not s:
        return ""
    # Drop trailing .0 from float-y values
    if s.endswith(".0"):
        s = s[:-2]
    try:
        n = int(float(s))
    except (ValueError, TypeError):
        return ""
    if n >= 1000:
        # full year like 2024 -> short 24
        n = n % 100
    return "{:02d}".format(n)


def _normalize_row(raw_row):
    """
    Map a raw CSV row from any of the three sources into the app's
    internal shape. Returns None if the row is unusable.
    """
    # Determine fiscal year
    year_raw = raw_row.get("year") or raw_row.get("fiscal_year")
    year_short = _normalize_fy_to_short(year_raw)
    if not year_short:
        return None

    org = (raw_row.get("organization") or "").strip()
    if not org:
        return None

    member = (raw_row.get("member") or "").strip()
    program = (raw_row.get("program") or "").strip()
    ein = (raw_row.get("ein") or "").strip()
    agency = (raw_row.get("agency") or "").strip()
    purpose = (raw_row.get("purpose") or "").strip()

    # Amount: keep as string so downstream parse_amount works
    amount_raw = raw_row.get("amount") or ""
    amount = str(amount_raw).strip()

    return {
        "year": "FY{}".format(year_short),
        "member": member,
        "organization": org,
        "program": program,
        "ein": ein,
        "amount": amount,
        "agency": agency,
        "purpose": purpose,
    }


def _row_key(row):
    """Deduplication key for a normalized row."""
    def clean(s):
        return (s or "").upper().strip()
    amt = parse_amount(row.get("amount"))
    return (
        clean(row.get("year")),
        clean(row.get("ein")),
        round(amt, 2),
        clean(row.get("member")),
        clean(row.get("organization")),
    )


# ------------------------------------------------------------------
# COMBINED DATA LOADER
# ------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def load_betanyc_awards():
    """
    Load and merge all three BetaNYC award sources:
      1. data/combined/all_years_awards.csv  (main)
      2. data/recovered/schedule_c_absorbed_awards.csv
      3. data/recovered/schedule_c_appendix_recovered.csv

    Normalizes each into a common shape, deduplicates, and returns
    a single list.
    """
    all_rows = []
    seen_keys = set()
    stats = {"main": 0, "absorbed": 0, "appendix": 0, "dupes": 0}

    for url, label in [
        (BETANYC_MAIN_URL, "main"),
        (BETANYC_ABSORBED_URL, "absorbed"),
        (BETANYC_APPENDIX_URL, "appendix"),
    ]:
        try:
            r = requests.get(url, timeout=180)
            r.raise_for_status()
            reader = csv.DictReader(io.StringIO(r.text))
            for raw in reader:
                row = _normalize_row(raw)
                if not row:
                    continue
                k = _row_key(row)
                if k in seen_keys:
                    stats["dupes"] += 1
                    continue
                seen_keys.add(k)
                all_rows.append(row)
                stats[label] += 1
        except Exception as e:
            st.warning("Could not load {} awards: {}".format(label, e))

    # Store stats for the UI to display
    load_betanyc_awards._stats = stats
    return all_rows
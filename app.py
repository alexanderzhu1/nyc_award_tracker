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

# Council Member surname -> district
COUNCIL_MEMBER_DISTRICTS = {
    "DE LA ROSA":     {"full_name": "Carmen De La Rosa",    "district": 10, "borough": "Manhattan/Bronx"},
    "RIVERA":         {"full_name": "Carlina Rivera",       "district": 2,  "borough": "Manhattan"},
    "EPSTEIN":        {"full_name": "Harvey Epstein",       "district": 2,  "borough": "Manhattan"},
    "AYALA":          {"full_name": "Diana Ayala",          "district": 8,  "borough": "Manhattan/Bronx"},
    "POWERS":         {"full_name": "Keith Powers",         "district": 4,  "borough": "Manhattan"},
    "MENIN":          {"full_name": "Julie Menin",          "district": 5,  "borough": "Manhattan"},
    "BREWER":         {"full_name": "Gale Brewer",          "district": 6,  "borough": "Manhattan"},
    "ABREU":          {"full_name": "Shaun Abreu",          "district": 7,  "borough": "Manhattan"},
    "RESTLER":        {"full_name": "Lincoln Restler",      "district": 33, "borough": "Brooklyn"},
    "LEVIN":          {"full_name": "Stephen Levin",        "district": 33, "borough": "Brooklyn"},
    "CHIN":           {"full_name": "Margaret Chin",        "district": 1,  "borough": "Manhattan"},
    "MARTE":          {"full_name": "Christopher Marte",    "district": 1,  "borough": "Manhattan"},
    "LANDER":         {"full_name": "Brad Lander",          "district": 39, "borough": "Brooklyn"},
    "HANIF":          {"full_name": "Shahana Hanif",        "district": 39, "borough": "Brooklyn"},
    "KALLOS":         {"full_name": "Ben Kallos",           "district": 5,  "borough": "Manhattan"},
    "RODRIGUEZ":      {"full_name": "Ydanis Rodriguez",     "district": 10, "borough": "Manhattan"},
    "SALAMANCA":      {"full_name": "Rafael Salamanca",     "district": 17, "borough": "Bronx"},
    "TORRES":         {"full_name": "Ritchie Torres",       "district": 15, "borough": "Bronx"},
    "GIBSON":         {"full_name": "Vanessa Gibson",       "district": 16, "borough": "Bronx"},
    "DIAZ":           {"full_name": "Rubén Díaz Sr.",       "district": 18, "borough": "Bronx"},
    "MILLER":         {"full_name": "I. Daneek Miller",     "district": 27, "borough": "Queens"},
    "RICHARDS":       {"full_name": "Donovan Richards",     "district": 31, "borough": "Queens"},
    "GRODENCHIK":     {"full_name": "Barry Grodenchik",     "district": 23, "borough": "Queens"},
    "VALLONE":        {"full_name": "Paul Vallone",         "district": 19, "borough": "Queens"},
    "CONSTANTINIDES": {"full_name": "Costa Constantinides","district": 22, "borough": "Queens"},
    "BRANNAN":        {"full_name": "Justin Brannan",       "district": 43, "borough": "Brooklyn"},
    "CUMMINGS":       {"full_name": "Laurie Cumbo",         "district": 35, "borough": "Brooklyn"},
    "CORNEGY":        {"full_name": "Robert Cornegy",       "district": 36, "borough": "Brooklyn"},
    "EUGENIO":        {"full_name": "Mathieu Eugene",       "district": 40, "borough": "Brooklyn"},
    "DEUTSCH":        {"full_name": "Chaim Deutsch",        "district": 48, "borough": "Brooklyn"},
    "TOUSSAINT":      {"full_name": "Farah Louis",          "district": 45, "borough": "Brooklyn"},
    "WILLIAMS":       {"full_name": "Jumaane Williams",     "district": 45, "borough": "Brooklyn"},
    "BARRON":         {"full_name": "Inez Barron",          "district": 42, "borough": "Brooklyn"},
    "MAISEL":         {"full_name": "Alan Maisel",          "district": 46, "borough": "Brooklyn"},
    "BORELLI":        {"full_name": "Joseph Borelli",       "district": 51, "borough": "Staten Island"},
    "ROSE":           {"full_name": "Deborah Rose",         "district": 49, "borough": "Staten Island"},
    "MATTEO":         {"full_name": "Steven Matteo",        "district": 50, "borough": "Staten Island"},
    "PALADINO":       {"full_name": "Vickie Paladino",      "district": 19, "borough": "Queens"},
    "ADAMS":          {"full_name": "Adrienne Adams",       "district": 28, "borough": "Queens"},
    "HOLDEN":         {"full_name": "Robert Holden",        "district": 30, "borough": "Queens"},
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
        for line in text.splitlines():
            if line.startswith("data: "):
                return json.loads(line[6:])
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
        try:
            content = response.get("result", {}).get("content", [])
            for item in content:
                if item.get("type") == "text":
                    return item.get("text", "")
        except Exception:
            pass
        return ""


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
        st.error(f"Could not load award data: {e}")
        return []


@st.cache_resource(show_spinner=False)
def get_mcp_client():
    client = DatabookMCPClient(DATABOOK_MCP_URL)
    client.initialize()
    return client


# ------------------------------------------------------------------
# TRACE LOGIC
# ------------------------------------------------------------------
def find_awards(rows, org_query):
    needle = org_query.upper()
    return [r for r in rows if needle in (r.get("organization") or "").upper()]


def resolve_district(member):
    if not member or member == "?":
        return None
    text = member.upper().strip()
    for surname, info in COUNCIL_MEMBER_DISTRICTS.items():
        if surname.upper() in text:
            return info
    return None


def parse_amount(value):
    try:
        return float(str(value).replace(",", "").replace("$", ""))
    except (ValueError, TypeError):
        return 0.0


def trace_nonprofit(org_query):
    result = {
        "awards": [],
        "contracts": [],
        "members": [],
        "unattributed": [],
        "single_member_warning": False,
    }

    rows = load_betanyc_awards()
    awards = find_awards(rows, org_query)
    if not awards:
        words = [w for w in org_query.upper().split() if len(w) > 3]
        if words:
            awards = find_awards(rows, words[0])
    result["awards"] = awards

    member_totals = {}
    unattributed = []

    for a in awards:
        member = (a.get("member") or "").strip()
        amount = parse_amount(a.get("amount"))

        if member and member != "?":
            if member not in member_totals:
                info = resolve_district(member)
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

    resolved = [m for m in member_totals.values() if m["info"] is not None]
    if len(resolved) < 2 and len(member_totals) >= 1:
        result["single_member_warning"] = True

    try:
        client = get_mcp_client()
        contract_resp = client.call_tool("search_contracts", {
            "vendor": org_query,
            "limit": 25,
        })
        contract_text = client.extract_text(contract_resp)
        result["contracts"] = parse_contract_blocks(contract_text)
    except Exception as e:
        st.warning(f"Contract lookup failed: {e}")

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
        for line in lines:
            line = line.strip()
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
        })
    return blocks


def is_discretionary(contract):
    title = (contract.get("title") or "").lower()
    return "discretionary" in title


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
    "Type a nonprofit name to see how Council discretionary funding "
    "became a contract, and whether it was paid."
)

with st.expander("How to use this", expanded=False):
    st.markdown(
        """
        **What this does:** traces a NYC Council discretionary award
        (sometimes called a "Schedule C" or "member item") from the
        moment it was designated through the registered contract and
        the payments recorded in Checkbook NYC.

        **How to use it:**
        1. Type a nonprofit name in the box below.
        2. Press Enter.
        3. Read the results, top to bottom.

        **Data sources:** BetaNYC's New-York-City-Budget repo,
        Databook.nyc, and the NYC Council roster.

        **What this is not:** it is not an official City source. Always
        verify against the original documents linked at the bottom.
        """
    )

org_query = st.text_input(
    "Nonprofit name",
    placeholder="e.g., Center for Community Alternatives",
).strip()

if org_query:
    with st.spinner("Tracing award → contract → payments..."):
        result = trace_nonprofit(org_query)

    st.subheader("Summary")

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
            "No results found. Try a shorter search term, or check the "
            "spelling of the nonprofit's legal name."
        )
        st.stop()

    if result["single_member_warning"]:
        st.warning(
            "⚠️ **Data completeness note:** The BetaNYC dataset only shows "
            "one Council Member for this organization. This may be due to a "
            "known parsing issue in the source data where award rows lose "
            "their boundaries during PDF extraction. Cross-check against "
            "the official Council Schedule C PDFs for the complete list of "
            "sponsoring Members."
        )

    if members:
        st.subheader("Council Members tied to these awards")
        for m in members:
            info = m["info"]
            if info:
                st.markdown(
                    f"**{info['full_name']}** — District {info['district']} "
                    f"({info['borough']})  \n"
                    f"${m['total']:,.0f} across {m['count']} award(s)"
                )
            else:
                st.markdown(
                    f"**{m['surname']}** — district not mapped  \n"
                    f"${m['total']:,.0f} across {m['count']} award(s)"
                )

        st.markdown("---")
            # --- MOCS tracker reference ---
        st.info(
            f"**Check official award status.** The MOCS Discretionary Award "
            f"Tracker is the authoritative source for whether an award has "
            f"been cleared. [Open the MOCS Tracker]({MOCS_TRACKER_URL}) and "
            f"search by EIN or organization name."
    )
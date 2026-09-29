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
import streamlit.components.v1 as components

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
        st.error("Could not load award data: {}".format(e))
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def get_all_organizations():
    rows = load_betanyc_awards()
    names = set()
    for r in rows:
        org = (r.get("organization") or "").strip()
        if org:
            names.add(org)
    return sorted(names)


@st.cache_resource(show_spinner=False)
def get_mcp_client():
    client = DatabookMCPClient(DATABOOK_MCP_URL)
    client.initialize()
    return client


# ------------------------------------------------------------------
# CUSTOM COMPONENT: JS AUTOCOMPLETE DROPDOWN (top 4 matches)
# ------------------------------------------------------------------
def org_autocomplete(organizations, key="org_autocomplete"):
    """
    Render a real HTML/JS autocomplete input.
    Shows at most the top 4 ranked matches.
    Sends the selected organization back to Streamlit via postMessage.
    """
    orgs_json = json.dumps(organizations)

    html = """
    <!DOCTYPE html>
    <html>
    <head>
      <style>
        body {
          margin: 0;
          font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
        }
        #wrap {
          position: relative;
          width: 100%;
        }
        #search {
          width: 100%;
          padding: 10px 12px;
          font-size: 16px;
          border: 1px solid #ccc;
          border-radius: 6px;
          box-sizing: border-box;
          outline: none;
        }
        #search:focus {
          border-color: #ff4b4b;
          box-shadow: 0 0 0 2px rgba(255,75,75,0.15);
        }
        #list {
          position: absolute;
          top: 100%;
          left: 0;
          right: 0;
          max-height: 220px;
          overflow-y: auto;
          background: white;
          border: 1px solid #ccc;
          border-top: none;
          border-radius: 0 0 6px 6px;
          z-index: 1000;
          display: none;
          box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }
        .item {
          padding: 10px 12px;
          cursor: pointer;
          font-size: 15px;
          border-bottom: 1px solid #f0f0f0;
        }
        .item:last-child { border-bottom: none; }
        .item:hover, .item.active {
          background: #ffeaea;
          color: #c0392b;
        }
        .item mark {
          background: #fff3b0;
          font-weight: bold;
          padding: 0 2px;
        }
        .empty {
          padding: 10px 12px;
          color: #888;
          font-size: 14px;
        }
      </style>
    </head>
    <body>
      <div id="wrap">
        <input id="search" type="text" placeholder="Start typing a nonprofit name..." autocomplete="off" />
        <div id="list"></div>
      </div>
      <script>
        const ORGS = __ORGS__;
        const input = document.getElementById('search');
        const list = document.getElementById('list');
        let activeIndex = -1;
        let currentMatches = [];

        function escapeHtml(s) {
          return s.replace(/[&<>"']/g, c => ({
            '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
          }[c]));
        }

        function highlight(org, query) {
          if (!query) return escapeHtml(org);
          const idx = org.toUpperCase().indexOf(query.toUpperCase());
          if (idx === -1) return escapeHtml(org);
          return escapeHtml(org.slice(0, idx))
            + '<mark>' + escapeHtml(org.slice(idx, idx + query.length)) + '</mark>'
            + escapeHtml(org.slice(idx + query.length));
        }

        function rankOrgs(query) {
          if (!query) return [];
          const q = query.toUpperCase().trim();
          const tokens = q.split(/\\s+/).filter(Boolean);
          const exact = [], starts = [], contains = [], tokensMatch = [];
          for (const org of ORGS) {
            const u = org.toUpperCase();
            if (u === q) exact.push(org);
            else if (u.startsWith(q)) starts.push(org);
            else if (u.includes(q)) contains.push(org);
            else if (tokens.length && tokens.every(t => u.includes(t))) tokensMatch.push(org);
          }
          return exact.concat(starts, contains, tokensMatch).slice(0, 4);
        }

        function render(matches, query) {
          list.innerHTML = '';
          if (!matches.length) {
            list.innerHTML = '<div class="empty">No matches</div>';
            list.style.display = 'block';
            return;
          }
          matches.forEach((org, i) => {
            const div = document.createElement('div');
            div.className = 'item' + (i === activeIndex ? ' active' : '');
            div.innerHTML = highlight(org, query);
            div.addEventListener('mousedown', (e) => {
              e.preventDefault();
              select(org);
            });
            list.appendChild(div);
          });
          list.style.display = 'block';
        }

        function select(org) {
          input.value = org;
          list.style.display = 'none';
          activeIndex = -1;
          sendValue(org);
        }

        function sendValue(value) {
          window.parent.postMessage({
            isStreamlitMessage: true,
            type: 'streamlit:setComponentValue',
            value: value,
          }, '*');
        }

        input.addEventListener('input', () => {
          const query = input.value;
          if (!query) {
            list.style.display = 'none';
            sendValue(null);
            return;
          }
          currentMatches = rankOrgs(query);
          activeIndex = -1;
          render(currentMatches, query);
        });

        input.addEventListener('keydown', (e) => {
          if (list.style.display === 'none') return;
          if (e.key === 'ArrowDown') {
            e.preventDefault();
            activeIndex = Math.min(activeIndex + 1, currentMatches.length - 1);
            render(currentMatches, input.value);
          } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            activeIndex = Math.max(activeIndex - 1, 0);
            render(currentMatches, input.value);
          } else if (e.key === 'Enter') {
            e.preventDefault();
            if (activeIndex >= 0) select(currentMatches[activeIndex]);
            else if (currentMatches.length) select(currentMatches[0]);
          } else if (e.key === 'Escape') {
            list.style.display = 'none';
          }
        });

        input.addEventListener('blur', () => {
          setTimeout(() => { list.style.display = 'none'; }, 150);
        });

        function sendReady() {
          window.parent.postMessage({
            isStreamlitMessage: true,
            type: 'streamlit:componentReady',
            apiVersion: 1,
          }, '*');
        }
        function setFrameHeight(h) {
          window.parent.postMessage({
            isStreamlitMessage: true,
            type: 'streamlit:setFrameHeight',
            height: h || document.body.scrollHeight,
          }, '*');
        }
        sendReady();
        setFrameHeight(80);
        window.addEventListener('resize', () => setFrameHeight(80));
      </script>
    </body>
    </html>
    """.replace("__ORGS__", orgs_json)

    return components.html(html, height=80, scrolling=False)


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


def member_display(m):
    info = m["info"]
    if info:
        title = "{} — District {} ({})".format(
            info["full_name"], info["district"], info["borough"]
        )
    else:
        title = "{} — district not mapped".format(m["surname"])
    subtitle = "${:,.0f} across {} award(s)".format(m["total"], m["count"])
    return title, subtitle


def member_matches_search(m, query):
    if not query:
        return True
    q = query.upper().strip()
    info = m["info"]
    haystack_parts = [m["surname"]]
    if info:
        haystack_parts += [
            info.get("full_name", ""),
            str(info.get("district", "")),
            info.get("borough", ""),
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
    "Type a nonprofit name to see how Council discretionary funding "
    "became a contract, and whether it was paid."
)

with st.expander("How to use this", expanded=False):
    st.markdown(
        """
        **What this does:** traces a NYC Council discretionary award
        from the moment it was designated through the registered
        contract and the payments recorded in Checkbook NYC.

        **How to use it:**
        1. Start typing a nonprofit name in the box below.
        2. Pick the matching organization from the dropdown.
        3. Click **Trace this organization**.
        4. Use the search box in the Council Members section to filter
           by member name, district, or borough.
        """
    )

st.markdown("### Find a nonprofit")

all_orgs = get_all_organizations()
org_autocomplete(all_orgs, key="org_autocomplete")

selected_org = st.session_state.get("selected_org")

if selected_org:
    st.success("Selected: **{}**".format(selected_org))
else:
    st.caption("Start typing to see matching organizations.")

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
            "No results found for this organization. This can happen "
            "when the organization appears in the source data under a "
            "slightly different legal name."
        )
        st.stop()

    if result["single_member_warning"]:
        st.warning(
            "Data completeness note: The BetaNYC dataset only shows one "
            "Council Member for this organization. This may be due to a "
            "known parsing issue in the source data. Cross-check against "
            "the official Council Schedule C PDFs and the MOCS "
            "Discretionary Award Tracker for the complete list."
        )

    st.info(
        "Check official award status. The MOCS Discretionary Award "
        "Tracker is the authoritative source for whether an award has "
        "been cleared. [Open the MOCS Tracker]({}) and search by EIN "
        "or organization name.".format(MOCS_TRACKER_URL)
    )

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

    if discretionary:
        st.subheader("Discretionary contracts")
        for c in discretionary:
            with st.container(border=True):
                st.markdown("**{}**".format(c["title"]))
                cols = st.columns(4)
                cols[0].markdown("**Vendor**  \n{}".format(c.get("vendor", "?")))
                cols[1].markdown("**Agency**  \n{}".format(c.get("agency", "?")))
                cols[2].markdown("**Amount**  \n${}".format(c.get("amount", "?")))
                cols[3].markdown("**Status**  \n{}".format(c.get("status", "?")))
                st.markdown("Term: {} -> {}".format(c.get("start", "?"),
                                                    c.get("end", "?")))
                if c.get("url"):
                    st.markdown("[View on Databook.nyc]({})".format(c["url"]))

    if contracts:
        st.subheader("All contracts found")
        contract_rows = []
        for c in contracts:
            contract_rows.append({
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

    st.divider()
    with st.expander("Sources and methodology"):
        st.markdown(
            "**Search term used:** `{}`\n\n"
            "**Data sources:**\n\n"
            "1. **BetaNYC New-York-City-Budget** — combined Schedule C awards. "
            "[GitHub repo](https://github.com/BetaNYC/New-York-City-Budget)\n\n"
            "2. **Databook.nyc** — MCP server joining MOCS contracts to "
            "Checkbook NYC payments. [databook.nyc](https://databook.nyc)\n\n"
            "3. **MOCS Discretionary Award Tracker** — official status of "
            "each discretionary award. [Open the tracker]({})\n\n"
            "4. **NYC Council roster** — member-to-district mapping. "
            "[council.nyc.gov](https://council.nyc.gov/districts/)\n\n"
            "**Known limitations:**\n\n"
            "- Parsing defect in source data. BetaNYC documents an open "
            "issue where some Schedule C award rows lose their boundaries "
            "during PDF extraction. Cross-check against official sources.\n"
            "- The `member` field is a surname only. The mapping table "
            "resolves it to a full name and district.\n"
            "- Some awards have a blank `member` field. These are usually "
            "Citywide Initiatives or fiscal sponsor awards.\n"
            "- Databook.nyc is a third-party service. If it is down, "
            "contract lookups will fail.\n"
            "- The MOCS Tracker is updated roughly every six weeks."
            .format(selected_org, MOCS_TRACKER_URL)
        )
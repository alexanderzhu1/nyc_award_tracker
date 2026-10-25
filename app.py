# -*- coding: utf-8 -*-
"""
app.py

NYC Council Discretionary Award Tracker
Category-first navigation.

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
# CONFIG & URLS
# ------------------------------------------------------------------
DATABOOK_MCP_URL = "https://api.databook.nyc/mcp"
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
MOCS_TRACKER_URL = (
    "https://www.nyc.gov/site/mocs/opportunities/"
    "discretionary-award-tracker.page"
)

# Friendly category names mapped to the raw CSV categories
CATEGORY_MAP = {
    "Youth & Education": ["YOUTH", "EDUCATION", "SCHOOL", "AFTER SCHOOL"],
    "Health & Human Services": ["HEALTH", "MENTAL", "HYGIENE", "SOCIAL", "HUMAN", "SENIOR", "AGING"],
    "Transportation & Infrastructure": ["TRANSPORT", "INFRASTRUCTURE", "STREET", "TRAFFIC"],
    "Housing & Community Development": ["HOUSING", "COMMUNITY", "DEVELOPMENT", "HOMELESS"],
    "Criminal Justice & Legal": ["CRIMINAL", "JUSTICE", "LEGAL", "COURT", "VICTIM"],
    "Arts & Culture": ["ARTS", "CULTURE", "LIBRARY", "MUSEUM"],
    "Environment & Parks": ["ENVIRONMENT", "PARK", "SANITATION", "CLEAN"],
    "Other / Unclassified": []  # catch-all
}


# ------------------------------------------------------------------
# MCP CLIENT (Unchanged)
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
# DATA LOADING & NORMALIZATION
# ------------------------------------------------------------------
def _normalize_fy(raw):
    s = str(raw or "").strip().upper().replace("FY", "")
    try:
        n = int(float(s))
        return "FY{:02d}".format(n % 100) if n >= 1000 else "FY{:02d}".format(n)
    except:
        return ""

def _normalize_row(row):
    year = _normalize_fy(row.get("year") or row.get("fiscal_year"))
    org = (row.get("organization") or "").strip()
    if not year or not org:
        return None
    return {
        "year": year,
        "member": (row.get("member") or "").strip(),
        "organization": org,
        "program": (row.get("program") or "").strip(),
        "ein": (row.get("ein") or "").strip(),
        "amount": str(row.get("amount") or "").strip(),
        "agency": (row.get("agency") or "").strip(),
        "category": (row.get("category") or "").strip().upper(),
    }

@st.cache_data(ttl=3600, show_spinner=False)
def load_all_awards():
    all_rows = []
    seen = set()
    
    for url in [BETANYC_MAIN_URL, BETANYC_ABSORBED_URL, BETANYC_APPENDIX_URL]:
        try:
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            reader = csv.DictReader(io.StringIO(r.text))
            for raw in reader:
                row = _normalize_row(raw)
                if not row: continue
                
                # Dedupe key
                key = (row["year"], row["ein"], row["amount"], row["member"], row["organization"])
                if key in seen: continue
                seen.add(key)
                
                # Assign friendly category
                matched_cat = "Other / Unclassified"
                raw_cat = row["category"]
                for friendly, keywords in CATEGORY_MAP.items():
                    if friendly == "Other / Unclassified": continue
                    if any(kw in raw_cat for kw in keywords):
                        matched_cat = friendly
                        break
                row["friendly_category"] = matched_cat
                
                all_rows.append(row)
        except Exception as e:
            st.warning(f"Failed to load data from {url}: {e}")
            
    return all_rows

def parse_amount(val):
    try:
        return float(str(val).replace(",", "").replace("$", ""))
    except:
        return 0.0

def get_mcp_client():
    client = DatabookMCPClient(DATABOOK_MCP_URL)
    client.initialize()
    return client


# ------------------------------------------------------------------
# CONTRACT PARSING
# ------------------------------------------------------------------
def parse_contracts(text):
    blocks = []
    parts = re.split(r"\n- \*\*", text)
    for part in parts[1:]:
        lines = part.split("\n")
        if not lines: continue
        title = lines[0].replace("**", "").rstrip(".").strip()
        vendor = agency = amount = status = start = end = url = contract_id = None
        for line in lines:
            line = line.strip()
            if contract_id is None:
                m = re.search(r"\b(CT\d{10,})\b", line)
                if m: contract_id = m.group(1)
            if line.startswith("Vendor:"):
                m = re.search(r"Vendor:\s*(.*?)\s*\|", line)
                if m: vendor = m.group(1).strip()
                m = re.search(r"Agency:\s*(.*)$", line)
                if m: agency = m.group(1).strip()
            elif line.startswith("Amount:"):
                m = re.search(r"Amount:\s*\$([\d,\.]+)", line)
                if m: amount = m.group(1)
                m = re.search(r"Status:\s*(.*)$", line)
                if m: status = m.group(1).strip()
            elif line.startswith("Start:"):
                m = re.search(r"Start:\s*(\S+)\s*\|\s*End:\s*(\S+)", line)
                if m: start, end = m.group(1), m.group(2)
            elif "Databook URL:" in line:
                m = re.search(r"(https://databook\.nyc/\S+)", line)
                if m: url = m.group(1)
        blocks.append({
            "title": title, "vendor": vendor, "agency": agency,
            "amount": amount, "status": status, "start": start,
            "end": end, "url": url, "contract_id": contract_id,
        })
    return blocks


# ------------------------------------------------------------------
# MAIN UI
# ------------------------------------------------------------------
st.set_page_config(page_title="NYC Discretionary Spending", layout="wide")

st.title("NYC Council Discretionary Spending")
st.markdown("Explore how the City Council allocates funding across different sectors.")

# 1. Load Data
with st.spinner("Loading award data..."):
    awards = load_all_awards()

if not awards:
    st.error("Could not load any data.")
    st.stop()

# 2. Sidebar: Category Selection
st.sidebar.header("Step 1: Choose a Sector")
categories = sorted(list(CATEGORY_MAP.keys()))
selected_category = st.sidebar.radio("Sectors", categories)

# Filter data by category
if selected_category == "Other / Unclassified":
    cat_awards = [a for a in awards if a["friendly_category"] == "Other / Unclassified"]
else:
    cat_awards = [a for a in awards if a["friendly_category"] == selected_category]

# Show high-level stats for this category
total_cat_amount = sum(parse_amount(a["amount"]) for a in cat_awards)
st.sidebar.markdown("---")
st.sidebar.metric(f"Total {selected_category} Funding", f"${total_cat_amount:,.0f}")
st.sidebar.caption(f"Based on {len(cat_awards)} award records.")

# 3. Main Area: Show Aggregated Projects
st.header(f"{selected_category} Projects")

if not cat_awards:
    st.info("No awards found in this category.")
    st.stop()

# Aggregate by Program/Project
projects = {}
for a in cat_awards:
    prog_name = a["program"] if a["program"] else "General Operating Support"
    if prog_name not in projects:
        projects[prog_name] = {"amount": 0.0, "count": 0, "orgs": set()}
    projects[prog_name]["amount"] += parse_amount(a["amount"])
    projects[prog_name]["count"] += 1
    projects[prog_name]["orgs"].add(a["organization"])

# Sort projects by amount descending
sorted_projects = sorted(projects.items(), key=lambda x: x[1]["amount"], reverse=True)

st.write("The Council funds the following projects in this sector. Click one to see the vendors.")

# Display projects as a grid of cards
cols = st.columns(3)
for i, (prog_name, data) in enumerate(sorted_projects):
    with cols[i % 3]:
        with st.container(border=True):
            st.subheader(prog_name)
            st.metric("Total Funding", f"${data['amount']:,.0f}")
            st.caption(f"{data['count']} awards across {len(data['orgs'])} organizations")
            
            if st.button(f"Explore Vendors", key=f"btn_{i}"):
                st.session_state["selected_project"] = prog_name

st.divider()

# 4. Deep Dive: Vendor Search within selected project
selected_proj = st.session_state.get("selected_project")

if selected_proj:
    st.header(f"Vendors for: {selected_proj}")
    
    # Get the orgs that received money for this specific project
    project_orgs = projects[selected_proj]["orgs"]
    sorted_orgs = sorted(list(project_orgs))
    
    # Interactive dropdown
    st.write("Search for a specific vendor that received funding for this project:")
    selected_org = st.selectbox(
        "Vendor Name (type to search)",
        options=[""] + sorted_orgs,
        format_func=lambda x: "Select a vendor..." if x == "" else x,
    )
    
    if selected_org:
        st.subheader(f"Trace: {selected_org}")
        
        # Filter awards for just this org AND this project
        org_awards = [a for a in cat_awards if a["organization"] == selected_org and (a["program"] == selected_proj or (not a["program"] and selected_proj == "General Operating Support"))]
        
        total_org_proj_amount = sum(parse_amount(a["amount"]) for a in org_awards)
        st.metric(f"Amount awarded to {selected_org} for this project", f"${total_org_proj_amount:,.0f}")
        
        # Show award records
        st.markdown("**Award Records**")
        table_rows = [{
            "Fiscal Year": a["year"],
            "Member": a["member"] or "Unattributed",
            "Agency": a["agency"],
            "Amount": f"${parse_amount(a['amount']):,.0f}"
        } for a in org_awards]
        st.dataframe(table_rows, use_container_width=True)
        
        # Fetch Contracts from Databook
        st.markdown("**Registered Contracts**")
        with st.spinner("Looking up contracts in Databook..."):
            try:
                client = get_mcp_client()
                
                # Clean up vendor name for Databook search
                search_name = selected_org.upper()
                for suffix in [", INC.", " INC.", ", LLC", " LLC", ", LTD."]:
                    if search_name.endswith(suffix):
                        search_name = search_name[:-len(suffix)]
                
                resp = client.call_tool("search_contracts", {"vendor": search_name, "limit": 10})
                text = client.extract_text(resp)
                contracts = parse_contracts(text)
                
                if not contracts:
                    st.info("No registered contracts found in Databook for this vendor.")
                else:
                    for c in contracts:
                        with st.expander(f"{c['title']} — ${c['amount']}"):
                            if c['contract_id']:
                                st.code(f"Contract ID: {c['contract_id']}", language="text")
                            st.write(f"**Agency:** {c['agency']}")
                            st.write(f"**Status:** {c['status']}")
                            st.write(f"**Term:** {c['start']} to {c['end']}")
                            if c['url']:
                                st.markdown(f"[View details on Databook.nyc]({c['url']})")
            except Exception as e:
                st.error(f"Failed to fetch contracts: {e}")
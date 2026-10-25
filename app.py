# -*- coding: utf-8 -*-
"""
app.py
NYC Council Discretionary Award Tracker
"""
import json
import csv
import io
import re
import requests
import streamlit as st
import pandas as pd

# --- CONFIG ---
DATABOOK_MCP_URL = "https://api.databook.nyc/mcp"
BETANYC_MAIN_URL = "https://raw.githubusercontent.com/BetaNYC/New-York-City-Budget/main/data/combined/all_years_awards.csv"
BETANYC_ABSORBED_URL = "https://raw.githubusercontent.com/BetaNYC/New-York-City-Budget/main/data/recovered/schedule_c_absorbed_awards.csv"
BETANYC_APPENDIX_URL = "https://raw.githubusercontent.com/BetaNYC/New-York-City-Budget/main/data/recovered/schedule_c_appendix_recovered.csv"

CATEGORY_MAP = {
    "Youth & Education": ["YOUTH", "EDUCATION", "SCHOOL", "AFTER SCHOOL"],
    "Health & Human Services": ["HEALTH", "MENTAL", "HYGIENE", "SOCIAL", "HUMAN", "SENIOR", "AGING"],
    "Housing & Community Development": ["HOUSING", "COMMUNITY", "DEVELOPMENT", "HOMELESS"],
    "Criminal Justice & Legal": ["CRIMINAL", "JUSTICE", "LEGAL", "COURT", "VICTIM"],
    "Environment & Parks": ["ENVIRONMENT", "PARK", "SANITATION", "CLEAN"],
    "Other / Unclassified": []
}

# --- MCP CLIENT ---
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
                try: parsed.append(json.loads(line[6:]))
                except json.JSONDecodeError: continue
        for obj in parsed:
            if isinstance(obj, dict) and ("result" in obj or "error" in obj): return obj
        if parsed: return parsed[-1]
        try: return json.loads(text)
        except json.JSONDecodeError: return {"raw": text}

    def _headers(self):
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.session_id: h["mcp-session-id"] = self.session_id
        return h

    def initialize(self):
        payload = {
            "jsonrpc": "2.0", "id": self._next_id(), "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "app", "version": "1"}}
        }
        r = self.session.post(self.endpoint, json=payload, headers=self._headers(), timeout=60)
        self.session_id = r.headers.get("mcp-session-id")

    def call_tool(self, name, arguments):
        payload = {"jsonrpc": "2.0", "id": self._next_id(), "method": "tools/call", "params": {"name": name, "arguments": arguments}}
        r = self.session.post(self.endpoint, json=payload, headers=self._headers(), timeout=60)
        return self._parse_sse(r.text)

    def extract_text(self, response):
        if not response: return ""
        try:
            content = response.get("result", {}).get("content", [])
            for item in content:
                if item.get("type") == "text": return item.get("text", "")
        except: pass
        return ""

# --- DATA LOADING ---
def _normalize_fy(raw):
    s = str(raw or "").strip().upper().replace("FY", "")
    try:
        n = int(float(s))
        return "FY{:02d}".format(n % 100) if n >= 1000 else "FY{:02d}".format(n)
    except: return ""

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
                year = _normalize_fy(raw.get("year") or raw.get("fiscal_year"))
                org = (raw.get("organization") or "").strip()
                if not year or not org: continue
                
                key = (year, raw.get("ein"), raw.get("amount"), raw.get("member"), org)
                if key in seen: continue
                seen.add(key)
                
                raw_cat = (raw.get("category") or "").strip().upper()
                friendly_cat = "Other / Unclassified"
                for fc, kws in CATEGORY_MAP.items():
                    if fc == "Other / Unclassified": continue
                    if any(kw in raw_cat for kw in kws):
                        friendly_cat = fc
                        break

                all_rows.append({
                    "Year": year,
                    "Member": (raw.get("member") or "").strip(),
                    "Organization": org,
                    "Program": (raw.get("program") or "").strip() or "General Operating Support",
                    "Amount": float(str(raw.get("amount") or "0").replace(",", "").replace("$", "").strip() or 0),
                    "Agency": (raw.get("agency") or "").strip(),
                    "Sector": friendly_cat
                })
        except Exception as e:
            st.warning(f"Failed to load {url}: {e}")
    return pd.DataFrame(all_rows)

# --- CONTRACT PARSING ---
def parse_contracts(text):
    blocks = []
    parts = re.split(r"\n- \*\*", text)
    for part in parts[1:]:
        lines = part.split("\n")
        if not lines: continue
        title = lines[0].replace("**", "").rstrip(".").strip()
        cid = vendor = agency = amount = status = start = end = url = None
        for line in lines:
            line = line.strip()
            if cid is None:
                m = re.search(r"\b(CT\d{10,})\b", line)
                if m: cid = m.group(1)
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
        blocks.append({"title": title, "vendor": vendor, "agency": agency, "amount": amount, "status": status, "start": start, "end": end, "url": url, "contract_id": cid})
    return blocks

# --- UI SETUP ---
st.set_page_config(page_title="NYC Discretionary Spending", layout="wide")

# Load Data once
with st.spinner("Loading data..."):
    df = load_all_awards()

# --- SIDEBAR (The Macro View) ---
st.sidebar.title("Filters")
selected_sector = st.sidebar.radio("Sector", sorted(df["Sector"].unique()))
selected_year = st.sidebar.selectbox("Fiscal Year", ["All Years"] + sorted(df["Year"].unique(), reverse=True))

# Filter DataFrame
filtered_df = df[df["Sector"] == selected_sector]
if selected_year != "All Years":
    filtered_df = filtered_df[filtered_df["Year"] == selected_year]

# Sidebar Stats
total_spend = filtered_df["Amount"].sum()
total_orgs = filtered_df["Organization"].nunique()
st.sidebar.markdown("---")
st.sidebar.metric(f"Total {selected_sector} Funding", f"${total_spend:,.0f}")
st.sidebar.caption(f"Distributed to {total_orgs} unique organizations across {len(filtered_df)} awards.")

# --- MAIN AREA (The Micro View) ---
st.title(f"{selected_sector} Funding")
if selected_year != "All Years":
    st.caption(f"Showing data for {selected_year}")

# 1. Search Bar (Global within sector)
st.markdown("### Find a Vendor")
search_query = st.text_input("Search by organization or program name", placeholder="e.g., Bronx Defenders, Youth Program...").strip()

if search_query:
    # Filter the dataframe by search query
    mask = filtered_df.apply(lambda row: search_query.lower() in str(row["Organization"]).lower() or search_query.lower() in str(row["Program"]).lower(), axis=1)
    search_results = filtered_df[mask]
    
    if search_results.empty:
        st.info("No organizations or programs match your search.")
    else:
        st.write(f"Found **{len(search_results)}** matching awards.")
        
        # Group by Organization to show a clean list
        for org, group in search_results.groupby("Organization"):
            org_total = group["Amount"].sum()
            with st.expander(f"{org} — ${org_total:,.0f}"):
                # Show award records
                st.markdown("**Award Records**")
                st.dataframe(group[["Year", "Member", "Program", "Agency", "Amount"]], hide_index=True, use_container_width=True)
                
                # Show contracts
                st.markdown("**Contracts (via Databook)**")
                with st.spinner("Fetching contracts..."):
                    try:
                        client = DatabookMCPClient(DATABOOK_MCP_URL)
                        client.initialize()
                        search_name = org.upper().split(",")[0].split(" INC")[0].strip()
                        resp = client.call_tool("search_contracts", {"vendor": search_name, "limit": 5})
                        text = client.extract_text(resp)
                        contracts = parse_contracts(text)
                        
                        if not contracts:
                            st.caption("No registered contracts found in Databook.")
                        else:
                            for c in contracts:
                                st.markdown(f"- [{c['title']}]({c['url']}) — ${c['amount']} ({c['status']}) | ID: `{c['contract_id']}`")
                    except Exception as e:
                        st.error(f"Could not load contracts: {e}")

else:
    # 2. Default View: Show Top Programs and Orgs
    st.markdown("### Top Programs in this Sector")
    
    # Aggregate by Program
    prog_summary = filtered_df.groupby("Program").agg(
        Total_Funding=("Amount", "sum"),
        Num_Awards=("Amount", "count"),
        Num_Orgs=("Organization", "nunique")
    ).sort_values("Total_Funding", ascending=False).reset_index()

    # Show top 5 programs as cards
    cols = st.columns(5)
    for i, row in prog_summary.head(5).iterrows():
        with cols[i]:
            st.metric(row["Program"], f"${row['Total_Funding']:,.0f}", f"{row['Num_Awards']} awards")

    st.markdown("### All Funded Projects")
    st.dataframe(
        prog_summary, 
        column_config={
            "Total_Funding": st.column_config.NumberColumn("Total Funding", format="$%d"),
            "Num_Awards": "Awards",
            "Num_Orgs": "Organizations"
        },
        hide_index=True,
        use_container_width=True
    )
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
BETANYC_MAIN_URL = "https://raw.githubusercontent.com/BetaNYC/New-York-City-Budget/main/data/combined/all_years_awards.csv"
BETANYC_ABSORBED_URL = "https://raw.githubusercontent.com/BetaNYC/New-York-City-Budget/main/data/recovered/schedule_c_absorbed_awards.csv"
BETANYC_APPENDIX_URL = "https://raw.githubusercontent.com/BetaNYC/New-York-City-Budget/main/data/recovered/schedule_c_appendix_recovered.csv"
CHECKBOOK_API = "https://www.checkbooknyc.com/api"

CATEGORY_MAP = {
    "Youth & Education": ["YOUTH", "EDUCATION", "SCHOOL", "AFTER SCHOOL"],
    "Health & Human Services": ["HEALTH", "MENTAL", "HYGIENE", "SOCIAL", "HUMAN", "SENIOR", "AGING"],
    "Housing & Community Development": ["HOUSING", "COMMUNITY", "DEVELOPMENT", "HOMELESS"],
    "Criminal Justice & Legal": ["CRIMINAL", "JUSTICE", "LEGAL", "COURT", "VICTIM"],
    "Arts & Culture": ["ARTS", "CULTURE", "LIBRARY", "MUSEUM"],
    "Environment & Parks": ["ENVIRONMENT", "PARK", "SANITATION", "CLEAN"],
    "Other / Unclassified": []
}

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
                    "Program": (raw.get("program") or "").strip() or "Unspecified / General Funding",
                    "Amount": float(str(raw.get("amount") or "0").replace(",", "").replace("$", "").strip() or 0),
                    "Agency": (raw.get("agency") or "").strip(),
                    "Sector": friendly_cat
                })
        except Exception as e:
            st.warning(f"Failed to load {url}: {e}")
    return pd.DataFrame(all_rows)

# --- CHECKBOOK API CONTRACT SEARCH ---
def fetch_checkbook_contracts(search_term):
    """
    Query Checkbook NYC API directly using the purpose field.
    This bypasses the broken vendor_name filter and finds contracts
    where the org name is mentioned in the description.
    """
    # Clean up the search term (remove commas, Inc, etc. to make the keyword broader)
    clean_term = search_term.upper().split(",")[0].replace(" INC", "").replace(" INC.", "").replace(" CORP", "").strip()
    
    xml_payload = f"""<request>
      <type_of_data>Contracts</type_of_data>
      <records_from>1</records_from>
      <max_records>10</max_records>
      <search_criteria>
        <criteria><name>purpose</name><value>{clean_term}</value></criteria>
        <criteria><name>status</name><value>registered</value></criteria>
      </search_criteria>
      <response_columns>
        <column>contract_id</column>
        <column>vendor_name</column>
        <column>agency</column>
        <column>amount</column>
        <column>registration_date</column>
        <column>start_date</column>
        <column>end_date</column>
        <column>purpose</column>
      </response_columns>
    </request>"""

    try:
        resp = requests.post(
            CHECKBOOK_API, 
            data=xml_payload.encode("utf-8"),
            headers={"Content-Type": "application/xml"},
            timeout=30
        )
        resp.raise_for_status()
        
        # Parse the XML response
        from xml.etree import ElementTree as ET
        root = ET.fromstring(resp.text)
        
        contracts = []
        for c in root.iter("contract"):
            contracts.append({
                "id": c.findtext("contract_id") or "No ID",
                "vendor": c.findtext("vendor_name") or "Unknown",
                "agency": c.findtext("agency") or "Unknown",
                "amount": c.findtext("amount") or "0",
                "reg_date": c.findtext("registration_date") or "Unknown",
                "start": c.findtext("start_date") or "Unknown",
                "end": c.findtext("end_date") or "Unknown",
                "purpose": c.findtext("purpose") or "No description"
            })
        return contracts
    except Exception as e:
        return [{"error": str(e)}]

# --- UI SETUP ---
st.set_page_config(page_title="NYC Discretionary Spending", layout="wide")
st.title("NYC Council Discretionary Spending")

with st.spinner("Loading data..."):
    df = load_all_awards()

# --- SIDEBAR ---
st.sidebar.title("Filters")
selected_sector = st.sidebar.radio("Sector", sorted(df["Sector"].unique()))
selected_year = st.sidebar.selectbox("Fiscal Year", ["All Years"] + sorted(df["Year"].unique(), reverse=True))

filtered_df = df[df["Sector"] == selected_sector]
if selected_year != "All Years":
    filtered_df = filtered_df[filtered_df["Year"] == selected_year]

total_spend = filtered_df["Amount"].sum()
total_orgs = filtered_df["Organization"].nunique()

st.sidebar.markdown("---")
amt_str = f"${total_spend/1_000_000_000:.2f}B" if total_spend >= 1_000_000_000 else f"${total_spend/1_000_000:.1f}M" if total_spend >= 1_000_000 else f"${total_spend:,.0f}"
st.sidebar.metric(f"Total {selected_sector} Funding", amt_str)
st.sidebar.caption(f"Distributed to {total_orgs} unique organizations across {len(filtered_df)} awards.")

# --- MAIN AREA ---
st.header(f"{selected_sector} Funding")
if selected_year != "All Years":
    st.caption(f"Showing data for {selected_year}")

st.markdown("### Find a Vendor")
search_query = st.text_input("Search by organization or program name", placeholder="e.g., Bronx Defenders, Youth Program...").strip()

if search_query:
    mask = filtered_df.apply(lambda row: search_query.lower() in str(row["Organization"]).lower() or search_query.lower() in str(row["Program"]).lower(), axis=1)
    search_results = filtered_df[mask]
    
    if search_results.empty:
        st.info("No organizations or programs match your search.")
    else:
        st.write(f"Found **{len(search_results)}** matching awards.")
        
        for org, group in search_results.groupby("Organization"):
            org_total = group["Amount"].sum()
            with st.expander(f"{org} — ${org_total:,.0f}"):
                st.markdown("**Award Records**")
                st.dataframe(group[["Year", "Member", "Program", "Agency", "Amount"]], hide_index=True, use_container_width=True)
                
                st.markdown("**Contracts (via Checkbook NYC API)**")
                with st.spinner("Searching Checkbook..."):
                    contracts = fetch_checkbook_contracts(org)
                    
                    if not contracts:
                        st.caption("No registered contracts found matching this vendor in Checkbook NYC.")
                    elif "error" in contracts[0]:
                        st.error(f"API Error: {contracts[0]['error']}")
                    else:
                        for c in contracts:
                            st.markdown(f"**Contract ID:** `{c['id']}`")
                            st.markdown(f"- **Vendor:** {c['vendor']}")
                            st.markdown(f"- **Agency:** {c['agency']}")
                            st.markdown(f"- **Amount:** ${c['amount']}")
                            st.markdown(f"- **Term:** {c['start']} to {c['end']}")
                            st.markdown(f"- **Purpose:** {c['purpose'][:200]}...")
                            st.divider()

else:
    st.markdown("### Top Programs in this Sector")
    
    prog_summary = filtered_df.groupby("Program").agg(
        Total_Funding=("Amount", "sum"),
        Num_Awards=("Amount", "count"),
        Num_Orgs=("Organization", "nunique")
    ).sort_values("Total_Funding", ascending=False).reset_index()

    cols = st.columns(5)
    for i, row in prog_summary.head(5).iterrows():
        val = f"${row['Total_Funding']/1_000_000_000:.2f}B" if row['Total_Funding'] >= 1_000_000_000 else f"${row['Total_Funding']/1_000_000:.1f}M" if row['Total_Funding'] >= 1_000_000 else f"${row['Total_Funding']:,.0f}"
        with cols[i]:
            st.metric(row["Program"], val, f"{row['Num_Awards']} awards")

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
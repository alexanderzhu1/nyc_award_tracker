# -*- coding: utf-8 -*-
"""
merge_workbooks.py

Compares the Council's funded disclosure workbooks against the
BetaNYC combined CSV. Reports rows present in one but not the other,
and rows present in both with mismatched fields.

Run:
    python merge_workbooks.py
"""

import csv
import io
import re
import sys
import requests

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------
BETANYC_CSV_URL = (
    "https://raw.githubusercontent.com/BetaNYC/"
    "New-York-City-Budget/main/data/combined/all_years_awards.csv"
)
WORKBOOK_URL_TEMPLATE = (
    "https://rnd.council.nyc.gov/src/assets/excelFund/"
    "funded_disclosure_FY{year}.xlsx"
)

# Fiscal years to compare. FY2024 is the first year the workbook
# includes the MOCS award number, but the workbook exists for earlier
# years too.
FISCAL_YEARS = [2024]


# ------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------
def normalize_name(s):
    s = (s or "").upper().strip()
    for prefix in ["THE ", "A ", "AN "]:
        if s.startswith(prefix):
            s = s[len(prefix):]
    for suffix in [", INC.", " INC.", ", INC", " INC",
                   " INCORPORATED", ", LTD.", " LTD."]:
        if s.endswith(suffix):
            s = s[:-len(suffix)]
    s = re.sub(r"[,;:]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def normalize_ein(ein):
    if ein is None:
        return ""
    s = str(ein).strip()
    s = s.replace("-", "").replace(" ", "").replace(".0", "")
    return s


def parse_amount(value):
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except (ValueError, TypeError):
        return 0.0


# ------------------------------------------------------------------
# LOAD BETA NYC CSV
# ------------------------------------------------------------------
def load_betanyc_rows(fiscal_years):
    print("Downloading BetaNYC CSV ...", flush=True)
    r = requests.get(BETANYC_CSV_URL, timeout=120)
    r.raise_for_status()
    reader = csv.DictReader(io.StringIO(r.text))
    rows = []
    for row in reader:
        year_raw = (row.get("year") or row.get("fiscal_year") or "").strip()
        year_raw = year_raw.replace("FY", "").replace("fy", "")
        try:
            year_short = int(year_raw)
        except (ValueError, TypeError):
            continue
        # Convert short year (e.g. 24) to full year (e.g. 2024)
        year_full = 2000 + year_short if year_short < 100 else year_short
        if year_full not in fiscal_years:
            continue
        rows.append({
            "source": "betanyc",
            "fiscal_year": year_full,
            "member": (row.get("member") or "").strip(),
            "organization": (row.get("organization") or "").strip(),
            "ein": normalize_ein(row.get("ein")),
            "amount": parse_amount(row.get("amount")),
            "agency": (row.get("agency") or "").strip(),
        })
    print("  {} BetaNYC rows for FY{}".format(
        len(rows), ", FY".join(str(y) for y in fiscal_years)), flush=True)
    return rows


# ------------------------------------------------------------------
# LOAD COUNCIL WORKBOOK
# ------------------------------------------------------------------
def load_workbook_rows(fiscal_year):
    try:
        import openpyxl
    except ImportError:
        print("ERROR: openpyxl is not installed.", flush=True)
        print("Run: pip install openpyxl", flush=True)
        sys.exit(1)

    url = WORKBOOK_URL_TEMPLATE.format(year=fiscal_year)
    print("Downloading workbook {} ...".format(url), flush=True)
    r = requests.get(url, timeout=120)
    r.raise_for_status()

    wb = openpyxl.load_workbook(io.BytesIO(r.content), read_only=True)
    ws = wb.active

    # Find the header row. Look at the first 10 rows for one that
    # contains the word "member" or "organization" or "legal name".
    header_row_idx = None
    rows = list(ws.iter_rows(values_only=True))
    for i, row in enumerate(rows[:10]):
        cells = [str(c).lower() if c else "" for c in row]
        joined = " ".join(cells)
        if "member" in joined and ("organization" in joined
                                   or "legal name" in joined
                                   or "program" in joined):
            header_row_idx = i
            break
    if header_row_idx is None:
        print("ERROR: Could not find header row in workbook.", flush=True)
        sys.exit(1)

    header = [str(c).strip() if c else "" for c in rows[header_row_idx]]
    print("  Header: {}".format(header), flush=True)

    # Map header names to our canonical fields
    def find_col(names):
        for i, h in enumerate(header):
            hl = h.lower()
            for name in names:
                if name in hl:
                    return i
        return None

    col_member = find_col(["member"])
    col_org = find_col(["organization", "legal name", "program"])
    col_ein = find_col(["ein"])
    col_amount = find_col(["amount"])
    col_agency = find_col(["agency"])

    if col_member is None or col_org is None:
        print("ERROR: Required columns not found.", flush=True)
        sys.exit(1)

    result = []
    for row in rows[header_row_idx + 1:]:
        if not row or not any(row):
            continue
        member = str(row[col_member] or "").strip() if col_member is not None else ""
        org = str(row[col_org] or "").strip() if col_org is not None else ""
        ein = normalize_ein(row[col_ein]) if col_ein is not None else ""
        amount = parse_amount(row[col_amount]) if col_amount is not None else 0.0
        agency = str(row[col_agency] or "").strip() if col_agency is not None else ""
        if not org and not member:
            continue
        result.append({
            "source": "workbook",
            "fiscal_year": fiscal_year,
            "member": member,
            "organization": org,
            "ein": ein,
            "amount": amount,
            "agency": agency,
        })

    print("  {} workbook rows for FY{}".format(len(result), fiscal_year),
          flush=True)
    return result


# ------------------------------------------------------------------
# COMPARE
# ------------------------------------------------------------------
def make_key(row):
    """Deduplication key: EIN + amount + fiscal year."""
    return (
        row["fiscal_year"],
        row["ein"] or normalize_name(row["organization"]),
        round(row["amount"], 2),
    )


def compare(workbook_rows, csv_rows):
    wb_keys = {}
    for r in workbook_rows:
        wb_keys.setdefault(make_key(r), []).append(r)
    csv_keys = {}
    for r in csv_rows:
        csv_keys.setdefault(make_key(r), []).append(r)

    only_in_workbook = []
    only_in_csv = []
    in_both = []

    for k, wb_list in wb_keys.items():
        if k in csv_keys:
            in_both.append((wb_list[0], csv_keys[k][0]))
        else:
            only_in_workbook.extend(wb_list)

    for k, csv_list in csv_keys.items():
        if k not in wb_keys:
            only_in_csv.extend(csv_list)

    return in_both, only_in_workbook, only_in_csv


def summarize(in_both, only_wb, only_csv, fiscal_year):
    print("\n" + "=" * 70, flush=True)
    print("FY{} Comparison".format(fiscal_year), flush=True)
    print("=" * 70, flush=True)
    print("Rows in both sources:        {}".format(len(in_both)), flush=True)
    print("Rows only in workbook:       {}".format(len(only_wb)), flush=True)
    print("Rows only in BetaNYC CSV:    {}".format(len(only_csv)), flush=True)
    total = len(in_both) + len(only_wb) + len(only_csv)
    if total:
        pct_wb = 100.0 * len(only_wb) / total
        pct_csv = 100.0 * len(only_csv) / total
        print("Workbook-only share:         {:.1f}%".format(pct_wb), flush=True)
        print("CSV-only share:              {:.1f}%".format(pct_csv), flush=True)


def write_reports(in_both, only_wb, only_csv, fiscal_year):
    # Rows in workbook but not in CSV — this is what the app is missing
    path1 = "gap_workbook_only_FY{}.csv".format(fiscal_year)
    with open(path1, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["fiscal_year", "member", "organization", "ein",
                    "amount", "agency"])
        for r in only_wb:
            w.writerow([r["fiscal_year"], r["member"], r["organization"],
                        r["ein"], r["amount"], r["agency"]])
    print("\nWrote {} rows to {}".format(len(only_wb), path1), flush=True)

    # Rows in CSV but not in workbook — these are extra or stale
    path2 = "gap_csv_only_FY{}.csv".format(fiscal_year)
    with open(path2, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["fiscal_year", "member", "organization", "ein",
                    "amount", "agency"])
        for r in only_csv:
            w.writerow([r["fiscal_year"], r["member"], r["organization"],
                        r["ein"], r["amount"], r["agency"]])
    print("Wrote {} rows to {}".format(len(only_csv), path2), flush=True)

    # Rows in both, for spot-checking field alignment
    path3 = "gap_in_both_FY{}.csv".format(fiscal_year)
    with open(path3, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["fiscal_year", "wb_member", "wb_org", "wb_ein",
                    "wb_amount", "csv_member", "csv_org", "csv_ein",
                    "csv_amount"])
        for wb, csv_row in in_both:
            w.writerow([fiscal_year, wb["member"], wb["organization"],
                        wb["ein"], wb["amount"],
                        csv_row["member"], csv_row["organization"],
                        csv_row["ein"], csv_row["amount"]])
    print("Wrote {} rows to {}".format(len(in_both), path3), flush=True)


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
def main():
    csv_rows = load_betanyc_rows(FISCAL_YEARS)

    for year in FISCAL_YEARS:
        wb_rows = load_workbook_rows(year)
        in_both, only_wb, only_csv = compare(wb_rows, csv_rows)
        summarize(in_both, only_wb, only_csv, year)
        write_reports(in_both, only_wb, only_csv, year)

    print("\nDone.", flush=True)


if __name__ == "__main__":
    main()
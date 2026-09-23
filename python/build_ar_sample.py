"""Build a PHI-safe A/R tracker from a Curve 90+ outstanding export.

Drops names. Maps responsible party / patient to IDs only.
Most recent visit and next appointment are demo dates (not PMS).
"""

from __future__ import annotations

import hashlib
import random
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.chart import PieChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "AR-Sample-Ledger.xlsx"
SOURCE = Path("/Users/haley/Documents/90OutstandingBalance_20260923.csv.xlsx")
SNAPSHOT = date(2026, 9, 23)

NAVY = "1B365D"
CREAM = "F4EFE4"
PINK = "FF88CF"
BLUE = "294BEF"
THIN = Border(
    left=Side(style="thin", color="D9D4C8"),
    right=Side(style="thin", color="D9D4C8"),
    top=Side(style="thin", color="D9D4C8"),
    bottom=Side(style="thin", color="D9D4C8"),
)
HEAD = Font(name="Calibri", bold=True, color=CREAM, size=11)
HEAD_FILL = PatternFill("solid", fgColor=NAVY)
MONEY = '"$"#,##0.00'
PCT = "0.0%"
DATE_FMT = "YYYY-MM-DD"


def _rng(key: str) -> random.Random:
    seed = int(hashlib.sha256(key.encode()).hexdigest()[:16], 16)
    return random.Random(seed)


def load_source(path: Path) -> list[tuple]:
    ws = load_workbook(path, data_only=True).active
    rows = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        rp, total, pt, ins = r[0], r[1], r[2], r[3]
        if rp is None or not isinstance(total, (int, float)):
            continue
        rows.append(r)
    return rows


def assign_ids(rows: list[tuple]) -> tuple[dict[str, str], dict[str, str]]:
    rp_ids: dict[str, str] = {}
    pt_ids: dict[str, str] = {}
    rp_n = 1001
    pt_n = 2001
    for r in rows:
        rp = str(r[0]).strip()
        pt = str(r[12]).strip() if r[12] else rp
        if rp not in rp_ids:
            rp_ids[rp] = f"RP-{rp_n}"
            rp_n += 1
        if pt not in pt_ids:
            pt_ids[pt] = f"P-{pt_n}"
            pt_n += 1
    return rp_ids, pt_ids


def demo_dates(patient_id: str, pt_over_90: float) -> tuple[date, date | None]:
    rng = _rng(patient_id)
    if pt_over_90 and pt_over_90 > 0:
        last = SNAPSHOT - timedelta(days=rng.randint(95, 400))
        nxt = None if rng.random() < 0.62 else SNAPSHOT + timedelta(days=rng.randint(3, 45))
    else:
        last = SNAPSHOT - timedelta(days=rng.randint(7, 120))
        nxt = None if rng.random() < 0.28 else SNAPSHOT + timedelta(days=rng.randint(1, 70))
    return last, nxt


def primary_bucket(pt90, pt61, pt31, pt0, ins90, ins61, ins31, ins0) -> str:
    vals = [
        ("90+", (pt90 or 0) + (ins90 or 0)),
        ("61–90", (pt61 or 0) + (ins61 or 0)),
        ("31–60", (pt31 or 0) + (ins31 or 0)),
        ("0–30", (pt0 or 0) + (ins0 or 0)),
    ]
    return max(vals, key=lambda x: x[1])[0]


def style_header(ws, row, cols):
    for i in range(1, cols + 1):
        c = ws.cell(row, i)
        c.font = HEAD
        c.fill = HEAD_FILL
        c.alignment = Alignment(horizontal="center", wrap_text=True, vertical="center")
        c.border = THIN
    ws.row_dimensions[row].height = 32


def widths(ws, sizes):
    for i, w in enumerate(sizes, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def build() -> None:
    raw = load_source(SOURCE)
    rp_ids, pt_ids = assign_ids(raw)

    wb = Workbook()

    # ----- Cover -----
    cover = wb.active
    cover.title = "About"
    cover["A1"] = "A/R tracker — 90+ outstanding (de-identified)"
    cover["A1"].font = Font(name="Calibri", bold=True, size=18, color=NAVY)
    cover.merge_cells("A1:F1")
    cover["A3"] = (
        "Names removed. Responsible party and patient are IDs only. "
        "Most recent visit and next appointment are demo dates for the portfolio workflow — not pulled from the PMS. "
        "Dollar aging is from the 23 Sep 2026 outstanding-balance extract."
    )
    cover["A3"].alignment = Alignment(wrap_text=True)
    cover.merge_cells("A3:F5")
    cover["A7"] = "Snapshot"
    cover["B7"] = SNAPSHOT
    cover["B7"].number_format = DATE_FMT
    cover["A8"] = "Accounts"
    cover["B8"] = len(raw)
    cover["A9"] = "See"
    cover["B9"] = "Ledger · Calcs · Aging pivot (tables + pie)"

    for addr in ("A7", "A8", "A9"):
        cover[addr].font = Font(bold=True, color=NAVY)
    widths(cover, [22, 28, 18, 18, 18, 18])

    # ----- Ledger -----
    led = wb.create_sheet("Ledger")
    headers = [
        "Responsible Party Patient ID",
        "Patient ID",
        "Most recent visit",
        "Next appointment",
        "Total owing",
        "Patient total owing",
        "Insurance total owing",
        "Patient 0–30",
        "Patient 31–60",
        "Patient 61–90",
        "Patient over 90",
        "Insurance 0–30",
        "Insurance 31–60",
        "Insurance 61–90",
        "Insurance over 90",
        "Primary bucket",
        "Has next appointment",
        "Days since last visit",
    ]
    for i, h in enumerate(headers, 1):
        led.cell(1, i, h)
    style_header(led, 1, len(headers))

    money_cols = range(5, 16)
    for i, r in enumerate(raw, 2):
        rp = str(r[0]).strip()
        pt_name = str(r[12]).strip() if r[12] else rp
        rid = rp_ids[rp]
        pid = pt_ids[pt_name]
        pt90 = r[7] or 0
        last, nxt = demo_dates(pid, pt90)
        bucket = primary_bucket(r[7], r[6], r[5], r[4], r[11], r[10], r[9], r[8])
        led.cell(i, 1, rid)
        led.cell(i, 2, pid)
        led.cell(i, 3, last).number_format = DATE_FMT
        nc = led.cell(i, 4, nxt if nxt else None)
        nc.number_format = DATE_FMT
        vals = [r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11]]
        for j, v in enumerate(vals, 5):
            cell = led.cell(i, j, float(v or 0))
            cell.number_format = MONEY
            cell.border = THIN
        led.cell(i, 16, bucket)
        led.cell(i, 17, "Yes" if nxt else "No")
        led.cell(i, 18, f"=DATE(2026,9,23)-C{i}")
        for col in (1, 2, 3, 4, 16, 17, 18):
            led.cell(i, col).border = THIN

    last_row = 1 + len(raw)
    for i in range(2, last_row + 1):
        led.cell(i, 18).number_format = "0"

    tab = Table(displayName="ARLedger", ref=f"A1:R{last_row}")
    tab.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    led.add_table(tab)
    led.auto_filter.ref = f"A1:R{last_row}"
    led.freeze_panes = "A2"
    widths(led, [28, 14, 18, 18, 14, 18, 20, 14, 14, 14, 16, 14, 14, 14, 16, 16, 20, 18])
    led.conditional_formatting.add(
        f"K2:K{last_row}",
        FormulaRule(formula=[f"K2>0"], fill=PatternFill("solid", fgColor="F8D0D4")),
    )

    n = last_row  # last data row

    # ----- Calcs -----
    calc = wb.create_sheet("Calcs")
    calc["A1"] = "Calculation tables"
    calc["A1"].font = Font(bold=True, size=16, color=NAVY)
    calc.merge_cells("A1:D1")

    calc["A3"] = "Headline"
    calc["A4"] = "Accounts"
    calc["B4"] = f"=COUNTA(Ledger!B2:B{n})"
    calc["A5"] = "Total owing"
    calc["B5"] = f"=SUM(Ledger!E2:E{n})"
    calc["B5"].number_format = MONEY
    calc["A6"] = "Patient owing"
    calc["B6"] = f"=SUM(Ledger!F2:F{n})"
    calc["B6"].number_format = MONEY
    calc["A7"] = "Insurance owing"
    calc["B7"] = f"=SUM(Ledger!G2:G{n})"
    calc["B7"].number_format = MONEY
    calc["A8"] = "Patient share of open"
    calc["B8"] = "=IF(B5=0,0,B6/B5)"
    calc["B8"].number_format = PCT
    calc["A9"] = "Patient over 90"
    calc["B9"] = f"=SUM(Ledger!K2:K{n})"
    calc["B9"].number_format = MONEY
    calc["A10"] = "90+ share of patient $"
    calc["B10"] = "=IF(B6=0,0,B9/B6)"
    calc["B10"].number_format = PCT
    calc["A11"] = "90+ accounts (patient $ > 0)"
    calc["B11"] = f'=COUNTIF(Ledger!K2:K{n},">0")'
    calc["A12"] = "90+ with no next appointment"
    calc["B12"] = f'=COUNTIFS(Ledger!K2:K{n},">0",Ledger!Q2:Q{n},"No")'
    calc["A13"] = "Unique responsible parties"
    calc["B13"] = f"=SUMPRODUCT(1/COUNTIF(Ledger!A2:A{n},Ledger!A2:A{n}))"
    calc["B13"].number_format = "0"

    calc["A15"] = "Aging mix — dollars"
    calc["A16"] = "Bucket"
    calc["B16"] = "Patient $"
    calc["C16"] = "Insurance $"
    calc["D16"] = "Total $"
    calc["E16"] = "Share"
    style_header(calc, 16, 5)
    buckets = [
        ("0–30", "H", "L"),
        ("31–60", "I", "M"),
        ("61–90", "J", "N"),
        ("90+", "K", "O"),
    ]
    for i, (label, pcol, icol) in enumerate(buckets, 17):
        calc.cell(i, 1, label)
        calc.cell(i, 2, f"=SUM(Ledger!{pcol}2:{pcol}{n})").number_format = MONEY
        calc.cell(i, 3, f"=SUM(Ledger!{icol}2:{icol}{n})").number_format = MONEY
        calc.cell(i, 4, f"=B{i}+C{i}").number_format = MONEY
        calc.cell(i, 5, f"=IF($D$21=0,0,D{i}/$D$21)").number_format = PCT
    calc["A21"] = "Total"
    calc["B21"] = "=SUM(B17:B20)"
    calc["C21"] = "=SUM(C17:C20)"
    calc["D21"] = "=SUM(D17:D20)"
    calc["E21"] = "=SUM(E17:E20)"
    for col in range(2, 5):
        calc.cell(21, col).number_format = MONEY
    calc["E21"].number_format = PCT
    for c in range(1, 6):
        calc.cell(21, c).font = Font(bold=True)

    calc["A23"] = "Huddle flags"
    calc["A24"] = "Patient 90+ and no next appointment (work first)"
    calc["B24"] = "=B12"
    calc["A25"] = "Open $ on those accounts"
    calc["B25"] = f'=SUMIFS(Ledger!E2:E{n},Ledger!K2:K{n},">0",Ledger!Q2:Q{n},"No")'
    calc["B25"].number_format = MONEY

    for addr in ("A3", "A15", "A23"):
        calc[addr].font = Font(bold=True, size=13, color=NAVY)
    for r in range(4, 14):
        calc.cell(r, 1).font = Font(bold=True)
    widths(calc, [44, 18, 16, 14, 12])

    # ----- Aging pivot (SUMIFS, live) -----
    pvt = wb.create_sheet("Aging pivot")
    pvt["A1"] = "Pivot — aging bucket × patient vs insurance"
    pvt["A1"].font = Font(bold=True, size=16, color=NAVY)
    pvt.merge_cells("A1:C1")
    pvt["A2"] = "Live SUMIFS off Ledger. Change a dollar on Ledger and this sheet moves."
    pvt["A4"] = "Primary bucket"
    pvt["B4"] = "Patient $"
    pvt["C4"] = "Insurance $"
    pvt["D4"] = "Accounts"
    pvt["E4"] = "No next appointment"
    style_header(pvt, 4, 5)
    for i, label in enumerate(["0–30", "31–60", "61–90", "90+"], 5):
        pvt.cell(i, 1, label)
        pvt.cell(i, 2, f'=SUMIF(Ledger!P:P,A{i},Ledger!F:F)').number_format = MONEY
        pvt.cell(i, 3, f'=SUMIF(Ledger!P:P,A{i},Ledger!G:G)').number_format = MONEY
        pvt.cell(i, 4, f'=COUNTIF(Ledger!P:P,A{i})')
        pvt.cell(i, 5, f'=COUNTIFS(Ledger!P:P,A{i},Ledger!Q:Q,"No")')
    pvt["A9"] = "Total"
    pvt["B9"] = "=SUM(B5:B8)"
    pvt["C9"] = "=SUM(C5:C8)"
    pvt["D9"] = "=SUM(D5:D8)"
    pvt["E9"] = "=SUM(E5:E8)"
    pvt["B9"].number_format = MONEY
    pvt["C9"].number_format = MONEY
    for c in range(1, 6):
        pvt.cell(9, c).font = Font(bold=True)

    pvt["A11"] = "Pivot — responsible party (open $ ≥ $200)"
    pvt["A11"].font = Font(bold=True, size=13, color=NAVY)
    pvt["A12"] = "Filter this table in Excel (Data → Filter) or insert a PivotTable from ARLedger."
    # Top RPs by summing in python for a static top-10 PLUS formula note
    from collections import defaultdict

    rp_tot: dict[str, float] = defaultdict(float)
    for r in raw:
        rp = rp_ids[str(r[0]).strip()]
        rp_tot[rp] += float(r[1] or 0)
    top = sorted(rp_tot.items(), key=lambda x: -x[1])[:15]
    pvt["A13"] = "Responsible Party Patient ID"
    pvt["B13"] = "Total owing"
    pvt["C13"] = "Patient $"
    pvt["D13"] = "Insurance $"
    style_header(pvt, 13, 4)
    for i, (rid, _) in enumerate(top, 14):
        pvt.cell(i, 1, rid)
        pvt.cell(i, 2, f'=SUMIF(Ledger!A:A,A{i},Ledger!E:E)').number_format = MONEY
        pvt.cell(i, 3, f'=SUMIF(Ledger!A:A,A{i},Ledger!F:F)').number_format = MONEY
    pvt.cell(i, 4, f'=SUMIF(Ledger!A:A,A{i},Ledger!G:G)').number_format = MONEY
    widths(pvt, [32, 18, 16, 16, 22])

    pvt["A30"] = "Next appointment"
    pvt["A30"].font = Font(bold=True, size=16, color=NAVY)
    pvt["A31"] = "Status"
    pvt["B31"] = "Patients"
    pvt["C31"] = "Open $"
    pvt["D31"] = "Share"
    style_header(pvt, 31, 4)
    pvt["A32"] = "Scheduled"
    pvt["B32"] = f'=COUNTIF(Ledger!Q2:Q{n},"Yes")'
    pvt["C32"] = f'=SUMIF(Ledger!Q2:Q{n},"Yes",Ledger!E2:E{n})'
    pvt["C32"].number_format = MONEY
    pvt["D32"] = "=IF($B$34=0,0,B32/$B$34)"
    pvt["D32"].number_format = PCT
    pvt["A33"] = "Not scheduled"
    pvt["B33"] = f'=COUNTIF(Ledger!Q2:Q{n},"No")'
    pvt["C33"] = f'=SUMIF(Ledger!Q2:Q{n},"No",Ledger!E2:E{n})'
    pvt["C33"].number_format = MONEY
    pvt["D33"] = "=IF($B$34=0,0,B33/$B$34)"
    pvt["D33"].number_format = PCT
    pvt["A34"] = "Total"
    pvt["B34"] = "=SUM(B32:B33)"
    pvt["C34"] = "=SUM(C32:C33)"
    pvt["C34"].number_format = MONEY
    pvt["D34"] = "=SUM(D32:D33)"
    pvt["D34"].number_format = PCT
    for c in range(1, 5):
        pvt.cell(34, c).font = Font(bold=True)

    pie = PieChart()
    pie.title = "Patients scheduled vs not scheduled"
    pie.add_data(Reference(pvt, min_col=2, min_row=31, max_row=33), titles_from_data=True)
    pie.set_categories(Reference(pvt, min_col=1, min_row=32, max_row=33))
    pie.dataLabels = DataLabelList()
    pie.dataLabels.showPercent = True
    pie.dataLabels.showCatName = True
    pie.dataLabels.showVal = True
    pie.width = 14
    pie.height = 10
    pie.style = 10
    pvt.add_chart(pie, "F30")

    calc.sheet_properties.tabColor = BLUE
    led.sheet_properties.tabColor = NAVY
    pvt.sheet_properties.tabColor = PINK

    wb.save(OUT)
    print(f"Wrote {OUT} rows={len(raw)} rps={len(rp_ids)} patients={len(pt_ids)}")


if __name__ == "__main__":
    build()

#!/usr/bin/env python3
"""Build a usable dental accounts-receivable Excel tracker."""

from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, NamedStyle, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.chart.series import DataPoint
from openpyxl.drawing.fill import PatternFillProperties, ColorChoice
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.drawing.line import LineProperties
from openpyxl.chart.marker import DataPoint as DP

TODAY = date(2026, 9, 22)
OUT = Path(__file__).resolve().parent / "Dental-AR-Tracker.xlsx"

BLACK = "0A0A0A"
CREAM = "F4EFE6"
IVORY = "FAF6F0"
GOLD = "C4A574"
MUTED = "8A8378"
RED = "8B2E2E"
AMBER = "B8860B"
GREEN = "2F5D3A"
WHITE = "FFFFFF"

thin = Border(
    left=Side(style="thin", color="D8D0C4"),
    right=Side(style="thin", color="D8D0C4"),
    top=Side(style="thin", color="D8D0C4"),
    bottom=Side(style="thin", color="D8D0C4"),
)


def fill(hex_color):
    return PatternFill("solid", fgColor=hex_color)


def font(name="Calibri", size=11, bold=False, color=BLACK, italic=False):
    return Font(name=name, size=size, bold=bold, color=color, italic=italic)


def apply_header(ws, row, cols, bg=BLACK, fg=CREAM):
    for col in range(1, cols + 1):
        cell = ws.cell(row, col)
        cell.fill = fill(bg)
        cell.font = font(size=10, bold=True, color=fg)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = 28


def money(cell):
    cell.number_format = '"$"#,##0.00'
    cell.alignment = Alignment(horizontal="right")


def dt(cell):
    cell.number_format = "YYYY-MM-DD"


def widths(ws, mapping):
    for col, width in mapping.items():
        ws.column_dimensions[col].width = width


# Fictional sample claims — no real PHI
ROWS = [
    # claim, patient_id, patient, provider, location, dos, billed, cdt, desc, payer,
    # charge, ins_paid, pat_paid, adj, bal_type, status, denial, follow, owner, notes
    ("CL-10421", "P-1008", "Rivera, A.", "Dr. Chen", "Main", TODAY - timedelta(days=12), TODAY - timedelta(days=10), "D0120", "Periodic oral eval", "Delta Dental", 68, 0, 0, 0, "Insurance", "Pending insurance", "", TODAY + timedelta(days=5), "Haley", "Awaiting ERA"),
    ("CL-10422", "P-1014", "Nguyen, T.", "Dr. Patel", "Main", TODAY - timedelta(days=18), TODAY - timedelta(days=16), "D1110", "Adult prophylaxis", "MetLife", 124, 86, 0, 0, "Patient", "Patient billed", "", TODAY + timedelta(days=2), "Haley", "EOB posted; $38 patient"),
    ("CL-10408", "P-1022", "Brooks, J.", "Dr. Chen", "North", TODAY - timedelta(days=41), TODAY - timedelta(days=38), "D2391", "Resin 1 surface post.", "Aetna", 215, 0, 0, 0, "Insurance", "Pending insurance", "", TODAY - timedelta(days=3), "Haley", "No ERA at 38 days — call payer"),
    ("CL-10390", "P-1003", "Okoye, M.", "Dr. Patel", "Main", TODAY - timedelta(days=62), TODAY - timedelta(days=58), "D2740", "Crown — porcelain/ceramic", "Cigna", 1285, 842, 0, 0, "Patient", "Patient billed", "", TODAY - timedelta(days=8), "Haley", "Statement 2 sent"),
    ("CL-10371", "P-1031", "Ellis, S.", "Dr. Chen", "Main", TODAY - timedelta(days=96), TODAY - timedelta(days=92), "D4341", "Perio scaling quadrant", "Delta Dental", 312, 0, 0, 0, "Insurance", "Denied — appeal", "Missing perio chart", TODAY + timedelta(days=1), "Haley", "Chart attached; appeal day 4"),
    ("CL-10430", "P-1019", "Hassan, L.", "Dr. Ruiz", "North", TODAY - timedelta(days=7), TODAY - timedelta(days=5), "D0150", "Comprehensive oral eval", "Guardian", 98, 0, 0, 0, "Insurance", "Pending insurance", "", TODAY + timedelta(days=12), "Haley", ""),
    ("CL-10355", "P-1001", "Park, H.", "Dr. Patel", "Main", TODAY - timedelta(days=121), TODAY - timedelta(days=118), "D2750", "Crown — PFM", "Aetna", 1140, 0, 0, 1140, "Closed", "Adjusted / written off", "Timely filing", "", "Office mgr", "Write-off approved 9/8"),
    ("CL-10418", "P-1027", "Diaz, C.", "Dr. Ruiz", "North", TODAY - timedelta(days=21), TODAY - timedelta(days=19), "D2392", "Resin 2 surface post.", "MetLife", 268, 174, 94, 0, "Closed", "Paid in full", "", "", "Haley", ""),
    ("CL-10402", "P-1011", "Walsh, K.", "Dr. Chen", "Main", TODAY - timedelta(days=49), TODAY - timedelta(days=46), "D0220", "Intraoral — first PA", "Medicaid", 42, 0, 0, 0, "Insurance", "Pending insurance", "", TODAY - timedelta(days=1), "Haley", "Portal shows in review"),
    ("CL-10388", "P-1006", "Ibrahim, N.", "Dr. Patel", "Main", TODAY - timedelta(days=74), TODAY - timedelta(days=70), "D6010", "Surgical implant", "Self-pay", 2450, 0, 800, 0, "Patient", "Payment plan", "", TODAY + timedelta(days=8), "Front desk", "Plan $400 / mo · 4 left"),
    ("CL-10425", "P-1033", "Grant, E.", "Dr. Chen", "North", TODAY - timedelta(days=9), TODAY - timedelta(days=8), "D0274", "Bitewings — four", "Delta Dental", 86, 69, 0, 0, "Patient", "Patient billed", "", TODAY + timedelta(days=6), "Haley", ""),
    ("CL-10364", "P-1016", "Sato, Y.", "Dr. Ruiz", "Main", TODAY - timedelta(days=108), TODAY - timedelta(days=104), "D8090", "Comp orthodontic treatment", "Cigna", 4200, 2100, 0, 0, "Patient", "Collections review", "", TODAY - timedelta(days=14), "Office mgr", "Balance 90+ · send to collections?"),
    ("CL-10411", "P-1024", "Miller, P.", "Dr. Patel", "Main", TODAY - timedelta(days=33), TODAY - timedelta(days=30), "D2140", "Amalgam 1 surface", "Guardian", 168, 0, 0, 0, "Insurance", "Denied — correct/resubmit", "Tooth number missing", TODAY + timedelta(days=0), "Haley", "Resubmit today"),
    ("CL-10433", "P-1009", "Cole, R.", "Dr. Chen", "North", TODAY - timedelta(days=4), TODAY - timedelta(days=3), "D1110", "Adult prophylaxis", "MetLife", 124, 0, 0, 0, "Insurance", "Pending insurance", "", TODAY + timedelta(days=14), "Haley", "Fresh claim"),
    ("CL-10397", "P-1029", "Bennett, F.", "Dr. Ruiz", "Main", TODAY - timedelta(days=55), TODAY - timedelta(days=52), "D3310", "Endo — anterior", "Aetna", 890, 623, 0, 0, "Patient", "Patient billed", "", TODAY - timedelta(days=5), "Haley", "Voicemail 9/17"),
    ("CL-10415", "P-1004", "Singh, D.", "Dr. Patel", "North", TODAY - timedelta(days=26), TODAY - timedelta(days=24), "D7140", "Extraction erupted tooth", "Delta Dental", 215, 172, 43, 0, "Closed", "Paid in full", "", "", "Haley", ""),
    ("CL-10380", "P-1018", "Young, B.", "Dr. Chen", "Main", TODAY - timedelta(days=83), TODAY - timedelta(days=80), "D4260", "Osseous surgery quadrant", "Cigna", 980, 0, 0, 0, "Insurance", "Pending insurance", "", TODAY - timedelta(days=10), "Haley", "Payer requested x-rays — sent 9/4"),
    ("CL-10428", "P-1035", "Ortiz, V.", "Dr. Ruiz", "North", TODAY - timedelta(days=6), TODAY - timedelta(days=5), "D1206", "Fluoride varnish", "Medicaid", 38, 38, 0, 0, "Closed", "Paid in full", "", "", "Haley", ""),
    ("CL-10392", "P-1012", "Klein, J.", "Dr. Patel", "Main", TODAY - timedelta(days=67), TODAY - timedelta(days=63), "D2950", "Core buildup", "Guardian", 285, 142, 0, 0, "Patient", "Patient billed", "", TODAY + timedelta(days=3), "Front desk", ""),
    ("CL-10406", "P-1020", "Adeyemi, K.", "Dr. Chen", "Main", TODAY - timedelta(days=44), TODAY - timedelta(days=41), "D0220", "Intraoral — first PA", "Self-pay", 42, 0, 0, 0, "Patient", "Patient billed", "", TODAY - timedelta(days=2), "Front desk", "No insurance on file"),
    ("CL-10377", "P-1007", "Foster, L.", "Dr. Ruiz", "North", TODAY - timedelta(days=91), TODAY - timedelta(days=88), "D2740", "Crown — porcelain/ceramic", "MetLife", 1285, 0, 0, 0, "Insurance", "Denied — appeal", "COB not on file", TODAY + timedelta(days=4), "Haley", "Waiting primary EOB from patient"),
    ("CL-10419", "P-1030", "Hale, M.", "Dr. Patel", "Main", TODAY - timedelta(days=15), TODAY - timedelta(days=14), "D0140", "Limited oral eval", "Aetna", 82, 57, 25, 0, "Closed", "Paid in full", "", "", "Haley", ""),
    ("CL-10399", "P-1015", "Qureshi, A.", "Dr. Chen", "North", TODAY - timedelta(days=51), TODAY - timedelta(days=48), "D4342", "Perio scaling 1-3 teeth", "Delta Dental", 198, 0, 0, 0, "Insurance", "Pending insurance", "", TODAY + timedelta(days=1), "Haley", ""),
    ("CL-10368", "P-1026", "Reed, S.", "Dr. Ruiz", "Main", TODAY - timedelta(days=112), TODAY - timedelta(days=109), "D5110", "Complete denture — maxillary", "Medicaid", 680, 420, 0, 0, "Patient", "Collections review", "", TODAY - timedelta(days=21), "Office mgr", "Patient unreachable"),
    ("CL-10431", "P-1002", "Vargas, I.", "Dr. Patel", "Main", TODAY - timedelta(days=3), TODAY - timedelta(days=2), "D0120", "Periodic oral eval", "Cigna", 68, 0, 0, 0, "Insurance", "Pending insurance", "", TODAY + timedelta(days=16), "Haley", ""),
]


def build():
    wb = Workbook()

    # ----- Lists -----
    lists = wb.active
    lists.title = "Lists"
    lists["A1"] = "Status"
    lists["B1"] = "Balance type"
    lists["C1"] = "Payer"
    lists["D1"] = "Location"
    lists["E1"] = "Owner"
    apply_header(lists, 1, 5)
    statuses = [
        "Pending insurance",
        "Denied — correct/resubmit",
        "Denied — appeal",
        "Patient billed",
        "Payment plan",
        "Collections review",
        "Paid in full",
        "Adjusted / written off",
    ]
    types = ["Insurance", "Patient", "Split", "Closed"]
    payers = ["Delta Dental", "MetLife", "Aetna", "Cigna", "Guardian", "Medicaid", "Self-pay"]
    locations = ["Main", "North"]
    owners = ["Haley", "Front desk", "Office mgr"]
    for i, v in enumerate(statuses, 2):
        lists.cell(i, 1, v)
    for i, v in enumerate(types, 2):
        lists.cell(i, 2, v)
    for i, v in enumerate(payers, 2):
        lists.cell(i, 3, v)
    for i, v in enumerate(locations, 2):
        lists.cell(i, 4, v)
    for i, v in enumerate(owners, 2):
        lists.cell(i, 5, v)
    lists.sheet_state = "hidden"
    widths(lists, {"A": 32, "B": 16, "C": 16, "D": 12, "E": 14})

    # ----- Ledger -----
    led = wb.create_sheet("AR Ledger", 0)
    headers = [
        "Claim ID", "Patient ID", "Patient (de-identified)", "Provider", "Location",
        "DOS", "Date billed", "CDT", "Description", "Payer",
        "Charge", "Insurance paid", "Patient paid", "Adjustment", "Balance",
        "Age (days)", "Aging bucket", "Balance type", "Status", "Denial / hold reason",
        "Next follow-up", "Owner", "Needs follow-up", "Notes",
    ]
    for col, h in enumerate(headers, 1):
        led.cell(1, col, h)
    apply_header(led, 1, len(headers))
    led.freeze_panes = "A2"
    led.auto_filter.ref = f"A1:X{len(ROWS)+1}"

    last = len(ROWS) + 1
    for i, r in enumerate(ROWS, 2):
        (
            claim, pid, name, prov, loc, dos, billed, cdt, desc, payer,
            charge, ins, pat, adj, btype, status, denial, follow, owner, notes,
        ) = r
        led.cell(i, 1, claim)
        led.cell(i, 2, pid)
        led.cell(i, 3, name)
        led.cell(i, 4, prov)
        led.cell(i, 5, loc)
        led.cell(i, 6, dos); dt(led.cell(i, 6))
        led.cell(i, 7, billed); dt(led.cell(i, 7))
        led.cell(i, 8, cdt)
        led.cell(i, 9, desc)
        led.cell(i, 10, payer)
        led.cell(i, 11, charge); money(led.cell(i, 11))
        led.cell(i, 12, ins); money(led.cell(i, 12))
        led.cell(i, 13, pat); money(led.cell(i, 13))
        led.cell(i, 14, adj); money(led.cell(i, 14))
        bal = led.cell(i, 15, f"=MAX(0,K{i}-L{i}-M{i}-N{i})")
        money(bal)
        age = led.cell(i, 16, f'=IF(G{i}="","",TODAY()-G{i})')
        age.alignment = Alignment(horizontal="center")
        led.cell(i, 17, f'=IF(O{i}=0,"—",IF(P{i}<=30,"0–30",IF(P{i}<=60,"31–60",IF(P{i}<=90,"61–90","90+"))))')
        led.cell(i, 18, btype)
        led.cell(i, 19, status)
        led.cell(i, 20, denial)
        if follow:
            led.cell(i, 21, follow); dt(led.cell(i, 21))
        else:
            led.cell(i, 21, "")
        led.cell(i, 22, owner)
        led.cell(
            i, 23,
            f'=IF(AND(O{i}>0,U{i}<>"",U{i}<=TODAY()),"Yes","No")',
        )
        led.cell(i, 24, notes)
        for col in range(1, 25):
            led.cell(i, col).border = thin
            led.cell(i, col).font = font(size=10)
            if i % 2 == 0:
                if led.cell(i, col).fill.fgColor is None or True:
                    if col not in ():
                        pass
        if i % 2 == 0:
            for col in range(1, 25):
                if led.cell(i, col).fill.fgColor.rgb in (None, "00000000"):
                    led.cell(i, col).fill = fill("FBF8F3")

    # data validation
    dv_status = DataValidation(type="list", formula1="=Lists!$A$2:$A$9", allow_blank=True)
    dv_type = DataValidation(type="list", formula1="=Lists!$B$2:$B$5", allow_blank=True)
    dv_payer = DataValidation(type="list", formula1="=Lists!$C$2:$C$8", allow_blank=True)
    dv_loc = DataValidation(type="list", formula1="=Lists!$D$2:$D$3", allow_blank=True)
    dv_owner = DataValidation(type="list", formula1="=Lists!$E$2:$E$4", allow_blank=True)
    for dv, col in (
        (dv_status, "S"),
        (dv_type, "R"),
        (dv_payer, "J"),
        (dv_loc, "E"),
        (dv_owner, "V"),
    ):
        dv.add(f"{col}2:{col}500")
        led.add_data_validation(dv)

    # aging color
    led.conditional_formatting.add(
        f"Q2:Q500",
        FormulaRule(formula=['Q2="90+"'], fill=fill("F3D6D6"), font=font(size=10, bold=True, color=RED)),
    )
    led.conditional_formatting.add(
        f"Q2:Q500",
        FormulaRule(formula=['Q2="61–90"'], fill=fill("F7E6C4"), font=font(size=10, color="7A5A10")),
    )
    led.conditional_formatting.add(
        f"W2:W500",
        FormulaRule(formula=['W2="Yes"'], fill=fill("F3D6D6"), font=font(size=10, bold=True, color=RED)),
    )

    widths(led, {
        "A": 12, "B": 12, "C": 22, "D": 12, "E": 10, "F": 12, "G": 12,
        "H": 10, "I": 26, "J": 14, "K": 12, "L": 14, "M": 13, "N": 12,
        "O": 12, "P": 11, "Q": 13, "R": 13, "S": 26, "T": 22, "U": 14,
        "V": 12, "W": 15, "X": 36,
    })
    led.auto_filter.ref = f"A1:X{max(last, 2)}"
    led.sheet_properties.pageSetUpPr.fitToPage = True
    led.page_setup.orientation = "landscape"
    led.page_setup.fitToWidth = 1
    led.page_setup.fitToHeight = 0
    led.oddHeader.left.text = "Dental A/R Ledger  ·  fictional sample — replace with your PMS export"
    led.print_title_rows = "1:1"

    # ----- Dashboard -----
    dash = wb.create_sheet("Dashboard", 0)
    dash.sheet_view.showGridLines = False
    dash["A1"] = "DENTAL ACCOUNTS RECEIVABLE"
    dash["A1"].font = font("Cambria", 22, True, BLACK)
    dash.merge_cells("A1:F1")
    dash["A2"] = "Operations tracker  ·  sample data as of 22 Sep 2026  ·  replace the ledger, keep the formulas"
    dash["A2"].font = font(size=11, italic=True, color=MUTED)
    dash.merge_cells("A2:F2")
    dash.row_dimensions[1].height = 32

    kpis = [
        (4, "B", "Total open A/R", f"=SUMIF('AR Ledger'!O:O,\">0\",'AR Ledger'!O:O)"),
        (4, "D", "Insurance A/R", f"=SUMIFS('AR Ledger'!O:O,'AR Ledger'!R:R,\"Insurance\",'AR Ledger'!O:O,\">0\")"),
        (4, "F", "Patient A/R", f"=SUMIFS('AR Ledger'!O:O,'AR Ledger'!R:R,\"Patient\",'AR Ledger'!O:O,\">0\")"),
        (8, "B", "Open claims", f"=COUNTIF('AR Ledger'!O:O,\">0\")"),
        (8, "D", "Follow-ups due", f"=COUNTIF('AR Ledger'!W:W,\"Yes\")"),
        (8, "F", "90+ days $", f"=SUMIF('AR Ledger'!Q:Q,\"90+\",'AR Ledger'!O:O)"),
    ]
    for row, col, label, formula in kpis:
        label_cell = dash[f"{col}{row}"]
        # label above value: use row-1
        dash[f"{col}{row - 1}"] = label
        dash[f"{col}{row - 1}"].font = font(size=9, bold=True, color=MUTED)
        dash[f"{col}{row}"] = formula
        dash[f"{col}{row}"].font = font("Cambria", 22, True, BLACK)
        if "COUNT" in formula:
            dash[f"{col}{row}"].number_format = "#,##0"
        else:
            dash[f"{col}{row}"].number_format = '"$"#,##0'
        dash[f"{col}{row}"].fill = fill(CREAM)
        dash[f"{col}{row}"].alignment = Alignment(horizontal="left")
        dash.merge_cells(start_row=row, start_column=ord(col) - 64, end_row=row, end_column=ord(col) - 64 + 1)
        dash.merge_cells(start_row=row - 1, start_column=ord(col) - 64, end_row=row - 1, end_column=ord(col) - 64 + 1)

    dash["B11"] = "Aging of open balances"
    dash["B11"].font = font("Cambria", 14, True)
    dash.merge_cells("B11:C11")
    dash["B12"] = "Bucket"
    dash["C12"] = "Open $"
    dash["D12"] = "% of A/R"
    apply_header(dash, 12, 4)
    dash["A12"] = ""
    buckets = ["0–30", "31–60", "61–90", "90+"]
    for i, b in enumerate(buckets):
        row = 13 + i
        dash.cell(row, 2, b)
        dash.cell(row, 3, f"=SUMIF('AR Ledger'!Q:Q,B{row},'AR Ledger'!O:O)")
        money(dash.cell(row, 3))
        dash.cell(row, 4, f"=IF(B4=0,0,C{row}/B4)")
        dash.cell(row, 4).number_format = "0.0%"
        for c in range(2, 5):
            dash.cell(row, c).border = thin
            dash.cell(row, c).font = font(size=11)

    dash["B18"] = "90+ as % of open A/R"
    dash["B18"].font = font(size=9, bold=True, color=MUTED)
    dash["B19"] = '=IF(B4=0,0,F8/B4)'
    dash["B19"].number_format = "0.0%"
    dash["B19"].font = font("Cambria", 22, True, RED)

    dash["E11"] = "Open $ by payer"
    dash["E11"].font = font("Cambria", 14, True)
    dash.merge_cells("E11:F11")
    dash["E12"] = "Payer"
    dash["F12"] = "Open $"
    apply_header(dash, 12, 6)
    for i, p in enumerate(payers):
        row = 13 + i
        dash.cell(row, 5, p)
        dash.cell(row, 6, f"=SUMIFS('AR Ledger'!O:O,'AR Ledger'!J:J,E{row},'AR Ledger'!O:O,\">0\")")
        money(dash.cell(row, 6))
        dash.cell(row, 5).border = thin
        dash.cell(row, 6).border = thin

    chart = BarChart()
    chart.type = "bar"
    chart.title = None
    chart.y_axis.title = None
    chart.x_axis.title = None
    chart.style = 10
    data = Reference(dash, min_col=3, min_row=12, max_row=16)
    cats = Reference(dash, min_col=2, min_row=13, max_row=16)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    chart.shape = 4
    chart.legend = None
    chart.width = 12
    chart.height = 7
    dash.add_chart(chart, "B22")

    dash["B32"] = "How to run this on Monday"
    dash["B32"].font = font("Cambria", 14, True)
    steps = [
        "1. Paste or enter new claims on AR Ledger. Do not type over columns O–Q or W — those are formulas.",
        "2. Set Next follow-up when you touch a claim. Dashboard “Follow-ups due” counts rows where that date is today or past and a balance remains.",
        "3. Filter Aging bucket = 90+ and Status not closed. That is the money at risk of write-off or collections.",
        "4. Split Insurance vs Patient A/R before the huddle. Insurance work is payer calls; patient work is statements and plans.",
        "5. When a claim pays, enter Insurance paid / Patient paid / Adjustment. Balance drops to $0 and aging goes to —.",
        "Sample patients are de-identified (P-####). Do not put real names or full member IDs in a shared file.",
    ]
    for i, s in enumerate(steps):
        dash.cell(33 + i, 2, s)
        dash.merge_cells(start_row=33 + i, start_column=2, end_row=33 + i, end_column=6)
        dash.cell(33 + i, 2).font = font(size=11)
        dash.row_dimensions[33 + i].height = 18

    widths(dash, {"A": 3, "B": 28, "C": 16, "D": 16, "E": 16, "F": 16, "G": 14})
    dash.row_dimensions[4].height = 32
    dash.row_dimensions[8].height = 32
    dash.print_area = "A1:F38"
    dash.page_setup.orientation = "landscape"
    dash.page_setup.fitToPage = True
    dash.page_setup.fitToWidth = 1
    dash.page_setup.fitToHeight = 1

    # ----- Follow-up -----
    fu = wb.create_sheet("Follow-up queue")
    fu["A1"] = "FOLLOW-UP QUEUE"
    fu["A1"].font = font("Cambria", 18, True)
    fu.merge_cells("A1:G1")
    fu["A2"] = "Filter the ledger where Needs follow-up = Yes, or use this working list. Add rows as you work the day."
    fu["A2"].font = font(size=11, italic=True, color=MUTED)
    fu.merge_cells("A2:G2")
    fu_headers = ["Claim ID", "Patient ID", "Payer", "Balance", "Status", "Next follow-up", "Owner", "Action today"]
    for col, h in enumerate(fu_headers, 1):
        fu.cell(4, col, h)
    apply_header(fu, 4, len(fu_headers))
    # Pull via formulas for first 25 ledger rows — user can copy down
    for i in range(5, 30):
        src = i - 3  # ledger row 2..
        fu.cell(i, 1, f"=IF('AR Ledger'!W{src}=\"Yes\",'AR Ledger'!A{src},\"\")")
        fu.cell(i, 2, f"=IF(A{i}=\"\",\"\",'AR Ledger'!B{src})")
        fu.cell(i, 3, f"=IF(A{i}=\"\",\"\",'AR Ledger'!J{src})")
        fu.cell(i, 4, f"=IF(A{i}=\"\",\"\",'AR Ledger'!O{src})")
        money(fu.cell(i, 4))
        fu.cell(i, 5, f"=IF(A{i}=\"\",\"\",'AR Ledger'!S{src})")
        fu.cell(i, 6, f"=IF(A{i}=\"\",\"\",'AR Ledger'!U{src})")
        dt(fu.cell(i, 6))
        fu.cell(i, 7, f"=IF(A{i}=\"\",\"\",'AR Ledger'!V{src})")
        fu.cell(i, 8, "")
    fu.auto_filter.ref = "A4:H29"
    widths(fu, {"A": 12, "B": 12, "C": 14, "D": 12, "E": 28, "F": 16, "G": 12, "H": 36})

    # ----- How to use -----
    how = wb.create_sheet("How to use", 0)
    how.sheet_view.showGridLines = False
    how["B2"] = "How to use this tracker"
    how["B2"].font = font("Cambria", 26, True)
    how.merge_cells("B2:F2")
    how["B3"] = "Built for a dental operations analyst  ·  Excel tables, not a PMS replacement"
    how["B3"].font = font(size=12, italic=True, color=MUTED)
    blocks = [
        ("What this is",
         "A working A/R book you can run every morning: open insurance vs patient dollars, aging, and a follow-up list. Dashboard numbers are live formulas against AR Ledger."),
        ("What you type",
         "On AR Ledger: claim, patient ID (not full name in a shared file), dates, CDT, payer, charge, payments, adjustments, status, next follow-up, owner, notes. Dropdowns sit on Location, Payer, Balance type, Status, and Owner."),
        ("What you never type over",
         "Balance (Charge − insurance paid − patient paid − adjustment), Age in days from Date billed, Aging bucket, and Needs follow-up (Yes when a balance remains and follow-up date is today or earlier)."),
        ("Daily rhythm",
         "Open Dashboard → work Follow-up queue → touch the ledger (payment, status, or a new follow-up date). 90+ and denied claims get the first hour. Patient A/R after insurance posts."),
        ("From your PMS",
         "Export claims with DOS, billed date, payer, charges, and payments. Paste values into columns A–N and R–V. Restore the formulas in O–Q and W if a paste wipes them (copy row 2 down)."),
        ("Privacy",
         "Sample rows use Patient ID P-#### and last-initial names. Keep real PHI in the PMS or a locked store. Do not email this file with live patient names."),
    ]
    row = 5
    for title, body in blocks:
        how.cell(row, 2, title).font = font("Cambria", 14, True)
        how.merge_cells(start_row=row + 1, start_column=2, end_row=row + 2, end_column=6)
        how.cell(row + 1, 2, body)
        how.cell(row + 1, 2).alignment = Alignment(wrap_text=True, vertical="top")
        how.cell(row + 1, 2).font = font(size=12)
        row += 4
    widths(how, {"A": 3, "B": 22, "C": 18, "D": 18, "E": 18, "F": 18})
    how.page_setup.fitToPage = True
    how.page_setup.fitToWidth = 1
    how.page_setup.fitToHeight = 1

    # tab colors
    how.sheet_properties.tabColor = GOLD
    dash.sheet_properties.tabColor = BLACK
    led.sheet_properties.tabColor = "8B2E2E"
    fu.sheet_properties.tabColor = AMBER

    wb.save(OUT)

    # Compute sample KPIs for the case study (same rules as formulas, using TODAY)
    open_rows = []
    for r in ROWS:
        charge, ins, pat, adj = r[10], r[11], r[12], r[13]
        bal = max(0, charge - ins - pat - adj)
        billed = r[6]
        age = (TODAY - billed).days
        bucket = "—" if bal == 0 else ("0–30" if age <= 30 else "31–60" if age <= 60 else "61–90" if age <= 90 else "90+")
        follow = r[17]
        needs = bal > 0 and follow != "" and follow <= TODAY
        open_rows.append({
            "bal": bal, "type": r[14], "bucket": bucket, "payer": r[9],
            "needs": needs, "open": bal > 0,
        })
    total = sum(x["bal"] for x in open_rows)
    ins_ar = sum(x["bal"] for x in open_rows if x["type"] == "Insurance")
    pat_ar = sum(x["bal"] for x in open_rows if x["type"] == "Patient")
    n_open = sum(1 for x in open_rows if x["open"])
    n_fu = sum(1 for x in open_rows if x["needs"])
    plus90 = sum(x["bal"] for x in open_rows if x["bucket"] == "90+")
    print("Wrote", OUT)
    print(f"Total AR ${total:,.2f}")
    print(f"Insurance ${ins_ar:,.2f}")
    print(f"Patient ${pat_ar:,.2f}")
    print(f"Open claims {n_open}")
    print(f"Follow-ups due {n_fu}")
    print(f"90+ ${plus90:,.2f} ({plus90/total:.1%})")
    for b in buckets:
        s = sum(x["bal"] for x in open_rows if x["bucket"] == b)
        print(f"  {b}: ${s:,.2f} ({s/total:.1%})")


if __name__ == "__main__":
    build()

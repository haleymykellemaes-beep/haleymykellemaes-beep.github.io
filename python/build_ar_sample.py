"""PHI-safe A/R sample: account number, DOS, patient balance, insurance balance.

No names. Fictional P-#### rows for the public portfolio.
"""

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

OUT = Path(__file__).resolve().parent.parent / "AR-Sample-Ledger.xlsx"

ROWS = [
    ("P-1042", "2025-04-03", 412.00, 0.00),
    ("P-1188", "2025-07-22", 0.00, 186.40),
    ("P-2310", "2025-08-14", 95.00, 240.00),
    ("P-2401", "2025-01-18", 620.50, 0.00),
    ("P-2519", "2025-06-09", 0.00, 310.00),
    ("P-2604", "2025-08-28", 40.00, 88.00),
    ("P-2711", "2025-03-12", 275.00, 0.00),
    ("P-2806", "2025-09-02", 0.00, 154.75),
    ("P-2914", "2025-05-27", 150.00, 150.00),
    ("P-3002", "2024-12-11", 890.00, 0.00),
    ("P-3108", "2025-07-01", 0.00, 425.00),
    ("P-3220", "2025-08-19", 60.00, 0.00),
    ("P-3345", "2025-02-06", 340.00, 0.00),
    ("P-3417", "2025-09-08", 0.00, 97.20),
    ("P-3551", "2025-04-29", 210.00, 75.00),
    ("P-3609", "2025-06-16", 0.00, 268.00),
    ("P-3722", "2025-01-30", 515.00, 0.00),
    ("P-3840", "2025-08-05", 25.00, 190.00),
    ("P-3901", "2025-03-21", 0.00, 0.00),
    ("P-4012", "2025-07-30", 180.00, 220.00),
]


def main() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sample ledger"

    header = Font(name="Calibri", bold=True, color="F4EFE4")
    head_fill = PatternFill("solid", fgColor="1B365D")
    money = '$#,##0.00'
    thin = Border(
        left=Side(style="thin", color="D9D4C8"),
        right=Side(style="thin", color="D9D4C8"),
        top=Side(style="thin", color="D9D4C8"),
        bottom=Side(style="thin", color="D9D4C8"),
    )

    ws["A1"] = "PHI-safe sample — fictional account numbers. No names."
    ws.merge_cells("A1:D1")
    ws["A1"].font = Font(name="Calibri", italic=True, color="5C6478", size=10)

    cols = [
        "Account number",
        "Date of service",
        "Patient balance due",
        "Insurance balance due",
    ]
    for i, name in enumerate(cols, 1):
        cell = ws.cell(3, i, name)
        cell.font = header
        cell.fill = head_fill
        cell.alignment = Alignment(horizontal="left")

    for r, row in enumerate(ROWS, 4):
        acct, dos, pt, ins = row
        ws.cell(r, 1, acct).border = thin
        c = ws.cell(r, 2, dos)
        c.number_format = "YYYY-MM-DD"
        c.border = thin
        pt_c = ws.cell(r, 3, pt)
        pt_c.number_format = money
        pt_c.border = thin
        ins_c = ws.cell(r, 4, ins)
        ins_c.number_format = money
        ins_c.border = thin

    last = 3 + len(ROWS)
    ws.cell(last + 2, 1, "Patient $ open")
    ws.cell(last + 2, 3, f"=SUM(C4:C{last})")
    ws.cell(last + 2, 3).number_format = money
    ws.cell(last + 3, 1, "Insurance $ open")
    ws.cell(last + 3, 4, f"=SUM(D4:D{last})")
    ws.cell(last + 3, 4).number_format = money

    widths = (20, 18, 22, 24)
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    wb.save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()

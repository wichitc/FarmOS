"""Report export (RPT-002: "at minimum CSV/PDF"). Generic over any list of
pydantic row models - a report function returns typed rows once, and both
export formats are derived from that same data via `.model_dump()`,
so a new report type gets CSV/PDF export for free rather than needing its
own formatting code.
"""
import csv
import io
from typing import Sequence

from pydantic import BaseModel
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle


def rows_to_csv(rows: Sequence[BaseModel]) -> str:
    if not rows:
        return ""
    fieldnames = list(rows[0].model_dump().keys())
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row.model_dump())
    return buffer.getvalue()


def rows_to_pdf(title: str, rows: Sequence[BaseModel]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), title=title)

    if not rows:
        table_data = [["(no data for the selected filters)"]]
    else:
        fieldnames = list(rows[0].model_dump().keys())
        table_data = [fieldnames] + [[str(v) if v is not None else "" for v in row.model_dump().values()] for row in rows]

    table = Table(table_data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d5a3d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
            ]
        )
    )
    doc.build([table])
    return buffer.getvalue()

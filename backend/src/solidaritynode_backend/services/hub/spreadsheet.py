"""CSV and XLSX exports that cannot run formulas (spreadsheet formula injection).

A cell whose text starts with ``=``, ``+``, ``-`` or ``@`` (or a tab or carriage return) is
read as a formula by spreadsheet programs. Every text cell of an exported report, template or
facility list is therefore **escaped** with a leading apostrophe (``'=1+1``), which spreadsheet
programs show as text. Numbers are written as numbers and are not escaped.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

__all__ = ["FORMULA_PREFIXES", "csv_bytes", "escape_cell", "xlsx_bytes"]

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

type Cell = str | int | float | None


def escape_cell(value: Cell) -> Cell:
    """Return ``value`` with a leading apostrophe if it is text a spreadsheet would run."""
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def csv_bytes(header: Sequence[str], rows: Iterable[Sequence[Cell]]) -> bytes:
    """Return a UTF-8 CSV (comma, header row) with every text cell escaped."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([escape_cell(h) for h in header])
    for row in rows:
        writer.writerow(["" if v is None else escape_cell(v) for v in row])
    return buffer.getvalue().encode("utf-8")


def xlsx_bytes(sheets: Sequence[tuple[str, Sequence[str], Iterable[Sequence[Cell]]]]) -> bytes:
    """Return an XLSX workbook with one sheet per ``(title, header, rows)``, cells escaped.

    The header row is bold and frozen; long text wraps.
    """
    workbook = Workbook()
    workbook.remove(workbook.active)  # type: ignore[arg-type]
    for title, header, rows in sheets:
        sheet = workbook.create_sheet(title)
        sheet.append([escape_cell(h) for h in header])
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for row in rows:
            sheet.append([escape_cell(v) for v in row])
        sheet.freeze_panes = "A2"
        for column in sheet.columns:
            width = max(len(str(c.value or "")) for c in column)
            letter = column[0].column_letter
            sheet.column_dimensions[letter].width = min(max(width + 2, 10), 80)
            for c in column:
                c.alignment = Alignment(wrap_text=True, vertical="top")
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()

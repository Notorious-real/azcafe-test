# ============================================================
#  AZ Cafe - Report exporters  (Phase 6E)
#  CSV        — plain, opens anywhere
#  XLSX       — real Excel workbook, written with the stdlib only
#  PDF        — real PDF (Courier, paginated), written with the stdlib
#
#  No third-party packages: the café machines stay dependency-free.
#  All three writers are pure functions over a list of session dicts,
#  so they are unit-testable without a display.
# ============================================================

import csv
import os
import zipfile
from datetime import datetime

PAGE_W, PAGE_H = 595.28, 841.89          # A4 portrait, points
MARGIN = 40.0
FONT_SIZE = 8.0
LINE_H = 10.0
COURIER_CHAR_W = 0.6                     # Courier advance width factor


def _money(currency: str, value) -> str:
    try:
        return f"{currency} {float(value):.0f}"
    except (TypeError, ValueError):
        return f"{currency} 0"


def _fmt_time(iso: str) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).strftime("%d-%m %H:%M")
    except ValueError:
        return str(iso)[:16]


def session_rows(sessions: list, currency: str = "Rs") -> list:
    """Normalised rows shared by all three exporters."""
    rows = []
    for s in sessions:
        user = (s.get("member_name") or s.get("guest_name")
                or (f"Member #{s.get('member_id')}" if s.get("member_id")
                    else "Guest"))
        rows.append([
            s.get("pc_name", ""),
            user,
            _fmt_time(s.get("start_time")),
            _fmt_time(s.get("end_time")) if s.get("end_time") else "running",
            int(s.get("duration_mins") or 0),
            _money(currency, s.get("amount_charged")),
            (s.get("payment_type") or "cash").title(),
            (s.get("status") or "").title(),
        ])
    return rows


HEADERS = ["PC", "Customer", "Started", "Ended", "Minutes", "Amount", "Payment", "Status"]


# ── CSV ─────────────────────────────────────────────────────

def export_csv(sessions: list, path: str, meta: dict) -> str:
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([meta.get("shop_name", "AZ Cafe"), meta.get("title", "Session report")])
        writer.writerow([meta.get("date", ""), meta.get("generated", "")])
        writer.writerow([])
        writer.writerow(HEADERS)
        writer.writerows(session_rows(sessions, meta.get("currency", "Rs")))
        writer.writerow([])
        writer.writerow(["TOTAL", "", "", "", "",
                         _money(meta.get("currency", "Rs"), meta.get("total", 0)), "", ""])
    return path


# ── XLSX (stdlib zipfile + OOXML) ───────────────────────────

def _xml_escape(text) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _xlsx_cell(ref: str, value, style: int = 0) -> str:
    style_attr = f' s="{style}"' if style else ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"{style_attr}><v>{value}</v></c>'
    return (f'<c r="{ref}"{style_attr} t="inlineStr"><is><t xml:space="preserve">'
            f'{_xml_escape(value)}</t></is></c>')


def _col_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def export_xlsx(sessions: list, path: str, meta: dict) -> str:
    """Minimal but valid xlsx (single sheet, inline strings)."""
    currency = meta.get("currency", "Rs")
    rows = session_rows(sessions, currency)
    total = meta.get("total")
    if total is None:
        total = sum(float(s.get("amount_charged") or 0) for s in sessions
                    if s.get("status") == "completed")

    sheet_rows = []
    r = 1
    sheet_rows.append(f'<row r="{r}">' + _xlsx_cell(f"A{r}", meta.get("shop_name", "AZ Cafe"), 1) + "</row>")
    r += 1
    sheet_rows.append(f'<row r="{r}">' + _xlsx_cell(f"A{r}", meta.get("title", "Session report")) + "</row>")
    r += 1
    sheet_rows.append(f'<row r="{r}">' + _xlsx_cell(f"A{r}", f"{meta.get('date','')}   generated {meta.get('generated','')}") + "</row>")
    r += 1
    sheet_rows.append(f'<row r="{r}"/>')
    r += 1

    header_cells = "".join(_xlsx_cell(f"{_col_letter(i)}{r}", h, 1)
                           for i, h in enumerate(HEADERS))
    sheet_rows.append(f'<row r="{r}">{header_cells}</row>')
    header_row = r
    r += 1

    for row in rows:
        cells = []
        for i, value in enumerate(row):
            if i == 4:                                   # minutes as a number
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    value = 0
            elif i == 5:                                 # strip the currency label
                value = float(str(value).replace(currency, "").strip() or 0)
            cells.append(_xlsx_cell(f"{_col_letter(i)}{r}", value))
        sheet_rows.append(f'<row r="{r}">{"".join(cells)}</row>')
        r += 1

    sheet_rows.append(f'<row r="{r}"/>')
    r += 1
    sheet_rows.append(
        f'<row r="{r}">' + _xlsx_cell(f"A{r}", "TOTAL", 1) +
        _xlsx_cell(f"F{r}", float(total or 0), 1) + "</row>")

    widths = "".join(
        f'<col min="{i+1}" max="{i+1}" width="{w}" customWidth="1"/>'
        for i, w in enumerate([14, 20, 14, 14, 10, 12, 10, 12]))
    freeze = f'<sheetView workbookViewId="0"><pane ySplit="{header_row}" topLeftCell="A{header_row+1}" activePane="bottomLeft" state="frozen"/></sheetView>'

    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<cols>{widths}</cols>'
        f'<sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    ).replace('<sheetData>', f'<sheetViews>{freeze}</sheetViews><sheetData>')

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Sessions" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '</Relationships>'
    )
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
        '<borders count="1"><border/></borders>'
        '<cellStyleXfs count="1"><xf/></cellStyleXfs>'
        '<cellXfs count="2"><xf xfId="0"/><xf xfId="0" fontId="1" applyFont="1"/></cellXfs>'
        '</styleSheet>'
    )

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/styles.xml", styles)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
    return path


# ── PDF (stdlib, Courier text report) ───────────────────────

def _pdf_escape(text) -> str:
    text = str(text)
    # Base-14 fonts are latin-1; drop anything exotic rather than break the file
    safe = text.encode("latin-1", errors="replace").decode("latin-1")
    return safe.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _fit(text: str, max_chars: int) -> str:
    text = str(text)
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


class _PDFBuilder:
    def __init__(self):
        self.objects = [None]          # 1-based object numbers

    def add(self, body: bytes) -> int:
        self.objects.append(body)
        return len(self.objects) - 1

    def reserve(self) -> int:
        self.objects.append(None)
        return len(self.objects) - 1

    def set(self, number: int, body: bytes):
        self.objects[number] = body

    def build(self) -> bytes:
        out = bytearray(b"%PDF-1.4\n")
        offsets = [0] * len(self.objects)
        for number in range(1, len(self.objects)):
            body = self.objects[number] or b""
            offsets[number] = len(out)
            out += f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
        xref_pos = len(out)
        count = len(self.objects)
        out += f"xref\n0 {count}\n".encode("ascii")
        out += b"0000000000 65535 f \n"
        for number in range(1, count):
            out += f"{offsets[number]:010d} 00000 n \n".encode("ascii")
        out += (f"trailer\n<< /Size {count} /Root 1 0 R >>\n"
                f"startxref\n{xref_pos}\n%%EOF\n").encode("ascii")
        return bytes(out)


def _text_page(lines: list, page_number: int, page_count: int) -> bytes:
    content = [b"BT"]
    y = PAGE_H - MARGIN
    for line in lines:
        size = line.get("size", FONT_SIZE)
        font = "/F2" if line.get("bold") else "/F1"
        x = MARGIN + line.get("indent", 0) * COURIER_CHAR_W * size
        content.append(f"/{font[1:]} {size} Tf".encode("ascii"))
        content.append(f"1 0 0 1 {x:.2f} {y:.2f} Tm".encode("ascii"))
        content.append(f"({_pdf_escape(line['text'])}) Tj".encode("latin-1", "replace"))
        y -= line.get("leading", LINE_H)
    footer = f"Page {page_number} / {page_count}"
    content.append(b"/F1 7 Tf")
    content.append(f"1 0 0 1 {PAGE_W - MARGIN - len(footer) * 4.2:.2f} {MARGIN - 14:.2f} Tm".encode("ascii"))
    content.append(f"({_pdf_escape(footer)}) Tj".encode("latin-1", "replace"))
    content.append(b"ET")
    return b"\n".join(content)


def export_pdf(sessions: list, path: str, meta: dict) -> str:
    """Paginated, print-ready PDF using the Courier base font."""
    currency = meta.get("currency", "Rs")
    rows = session_rows(sessions, currency)
    total = meta.get("total")
    if total is None:
        total = sum(float(s.get("amount_charged") or 0) for s in sessions
                    if s.get("status") == "completed")

    usable_w = PAGE_W - 2 * MARGIN
    max_chars = int(usable_w / (FONT_SIZE * COURIER_CHAR_W))
    header_line = (f"{'PC':<12}{'Customer':<20}{'Started':<12}{'Ended':<12}"
                   f"{'Min':>5}  {'Amount':>11}  {'Pay':<8}{'Status':<10}")

    first = [
        {"text": meta.get("shop_name", "AZ Cafe"), "size": 16, "bold": True, "leading": 22},
        {"text": meta.get("title", "Session report"), "size": 11, "bold": True, "leading": 16},
        {"text": f"{meta.get('date','')}       generated {meta.get('generated','')}",
         "size": 8, "leading": 14},
        {"text": "", "size": 8, "leading": 8},
        {"text": header_line, "size": FONT_SIZE, "bold": True},
        {"text": "-" * min(len(header_line), max_chars), "size": FONT_SIZE},
    ]
    body = []
    for row in rows:
        pc, customer, started, ended, minutes, amount, payment, status = row
        body.append({
            "text": (f"{_fit(pc, 12):<12}{_fit(customer, 20):<20}"
                     f"{started:<12}{ended:<12}{minutes:>5}  {amount:>11}  "
                     f"{payment:<8}{status:<10}"),
            "size": FONT_SIZE,
        })
    if not body:
        body.append({"text": "No sessions for this period.", "size": FONT_SIZE})

    summary = [
        {"text": "", "size": FONT_SIZE, "leading": 8},
        {"text": "-" * min(len(header_line), max_chars), "size": FONT_SIZE},
        {"text": f"Sessions shown: {len(rows)}    Revenue (settled): {_money(currency, total)}",
         "size": 9, "bold": True},
    ]

    per_page = int((PAGE_H - 2 * MARGIN - 90) / LINE_H) - 6
    chunks = [first + body[i:i + per_page]
              for i in range(0, max(len(body), 1), per_page)]
    chunks[-1] = chunks[-1] + summary

    builder = _PDFBuilder()
    catalog = builder.reserve()
    pages_obj = builder.reserve()
    font1 = builder.add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
    font2 = builder.add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold >>")

    page_ids = []
    for index, lines in enumerate(chunks, start=1):
        stream = _text_page(lines, index, len(chunks))
        content_id = builder.add(
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream")
        page_id = builder.add(
            (f"<< /Type /Page /Parent {pages_obj} 0 R "
             f"/MediaBox [0 0 {PAGE_W:.2f} {PAGE_H:.2f}] "
             f"/Resources << /Font << /F1 {font1} 0 R /F2 {font2} 0 R >> >> "
             f"/Contents {content_id} 0 R >>").encode("ascii"))
        page_ids.append(page_id)

    builder.set(pages_obj, (
        f"<< /Type /Pages /Count {len(page_ids)} /Kids ["
        + " ".join(f"{pid} 0 R" for pid in page_ids) + "] >>").encode("ascii"))
    builder.set(catalog, f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode("ascii"))

    with open(path, "wb") as handle:
        handle.write(builder.build())
    return path


# ── Helpers used by the UI ──────────────────────────────────

def default_meta(shop_name: str, title: str, date_str: str, currency: str,
                 sessions: list = None) -> dict:
    total = None
    if sessions is not None:
        total = sum(float(s.get("amount_charged") or 0) for s in sessions
                    if s.get("status") == "completed")
    return {
        "shop_name": shop_name or "AZ Cafe",
        "title": title,
        "date": date_str,
        "currency": currency,
        "generated": datetime.now().strftime("%d-%m-%Y %H:%M"),
        "total": total,
    }


def suggested_name(prefix: str, date_str: str, extension: str) -> str:
    safe = prefix.replace(" ", "_").lower()
    return f"azcafe_{safe}_{date_str}.{extension}"


def export_any(fmt: str, sessions: list, path: str, meta: dict) -> str:
    fmt = fmt.lower()
    if fmt == "csv":
        return export_csv(sessions, path, meta)
    if fmt == "xlsx":
        return export_xlsx(sessions, path, meta)
    if fmt == "pdf":
        return export_pdf(sessions, path, meta)
    raise ValueError(f"Unknown export format: {fmt}")


def ensure_extension(path: str, extension: str) -> str:
    if not os.path.splitext(path)[1]:
        return f"{path}.{extension}"
    return path

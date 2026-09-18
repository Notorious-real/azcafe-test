# ============================================================
#  AZ Cafe - Receipt printing  (Phase 7B)
#
#  Windows: sends a plain-text receipt (32 columns, thermal-printer
#  friendly) to the Windows print spooler — either the default printer
#  or one the operator picked in Settings.
#  Other platforms: a no-op that reports politely, so the app still runs
#  (dev/tests run on Linux).
#
#  Everything is best-effort and never raises into the UI.
# ============================================================

import os
import subprocess
import sys
import tempfile
from datetime import datetime

import applog

log = applog.get_logger("printer")

WIDTH = 32          # characters — 58 mm thermal printers


def is_supported() -> bool:
    return sys.platform.startswith("win")


def list_printers() -> list:
    """Names of installed printers, [] when unknown."""
    if not is_supported():
        return []

    # pywin32 is the cleanest source when it happens to be installed
    try:
        import win32print                                      # type: ignore
        return [p[2] for p in win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
    except Exception:                                          # noqa: BLE001
        pass

    for command in (
        ["powershell", "-NoProfile", "-Command",
         "Get-Printer | Select-Object -ExpandProperty Name"],
        ["wmic", "printer", "get", "name"],
    ):
        try:
            result = subprocess.run(command, capture_output=True, text=True,
                                    timeout=8, shell=False)
            names = [line.strip() for line in (result.stdout or "").splitlines()]
            names = [n for n in names if n and n.lower() != "name"]
            if names:
                return names
        except (OSError, subprocess.SubprocessError):
            continue
    return []


def platform_note() -> str:
    """Short explanation shown in the Settings → Printer tab."""
    if is_supported():
        return "Receipts are sent to the Windows print spooler."
    return ("Receipt printing is Windows-only. On this machine receipts are "
            "shown on screen and can be saved as a text file.")


def default_printer_name() -> str:
    try:
        import win32print                                      # type: ignore
        return win32print.GetDefaultPrinter()
    except Exception:                                          # noqa: BLE001
        return ""


def build_receipt_text(info: dict, shop_name: str = "AZ Cafe",
                       currency: str = "Rs") -> str:
    """
    info keys: pc_name, user, started, ended, booked_mins, used_secs,
               prepaid, charged, refund, payment_type, session_id, balance_left
    """
    def line(char="-"):
        return char * WIDTH

    def row(label, value):
        value = str(value)
        space = max(1, WIDTH - len(label) - len(value))
        return f"{label}{' ' * space}{value}"

    used = int(info.get("used_secs") or 0)
    used_txt = f"{used // 3600:d}h {(used % 3600) // 60:02d}m {used % 60:02d}s"
    booked = info.get("booked_mins")

    out = [
        shop_name.center(WIDTH),
        "SESSION RECEIPT".center(WIDTH),
        line("="),
        row("Receipt #", info.get("session_id", "-")),
        row("PC", info.get("pc_name", "-")),
        row("Customer", info.get("user", "Guest")),
        row("Payment", str(info.get("payment_type", "cash")).title()),
        line(),
        row("Started", _short_time(info.get("started"))),
        row("Ended", _short_time(info.get("ended"))),
        row("Time booked", f"{booked} min" if booked else "-"),
        row("Time used", used_txt),
        line(),
        row("Prepaid", f"{currency} {float(info.get('prepaid') or 0):.0f}"),
        row("Charged", f"{currency} {float(info.get('charged') or 0):.0f}"),
    ]
    refund = float(info.get("refund") or 0)
    if refund > 0:
        out.append(row("Refunded", f"{currency} {refund:.0f}"))
    balance_left = info.get("balance_left")
    if balance_left is not None:
        out.append(row("Balance left", f"{currency} {float(balance_left):.0f}"))
    out += [
        line("="),
        "Thank you!".center(WIDTH),
        datetime.now().strftime("%d-%m-%Y %I:%M %p").center(WIDTH),
        "",
        "",
    ]
    return "\n".join(out)


def _short_time(iso) -> str:
    if not iso:
        return "-"
    try:
        return datetime.fromisoformat(str(iso)).strftime("%d-%m %H:%M")
    except ValueError:
        return str(iso)[:16]


def print_text(text: str, printer_name: str = "", copies: int = 1) -> tuple:
    """
    Send plain text to a printer.
    Returns (ok: bool, message: str).
    """
    if not is_supported():
        return False, "Receipt printing is only available on Windows."
    if not text.strip():
        return False, "Nothing to print."

    path = os.path.join(tempfile.gettempdir(),
                        f"azcafe_receipt_{datetime.now():%Y%m%d_%H%M%S}.txt")
    try:
        # Thermal printers want CRLF
        with open(path, "w", encoding="utf-8", newline="\r\n") as handle:
            handle.write(text)
    except OSError as exc:
        log.warning("Could not write receipt file: %s", exc)
        return False, f"Could not write the receipt file: {exc}"

    for _ in range(max(1, copies)):
        ok, message = _spool(path, printer_name)
        if not ok:
            return False, message
    return True, "Receipt sent to the printer."


def _spool(path: str, printer_name: str) -> tuple:
    if printer_name:
        try:
            result = subprocess.run(
                f'print /D:"{printer_name}" "{path}"',
                shell=True, capture_output=True, text=True, timeout=20)
            if result.returncode == 0:
                return True, "Sent."
            log.warning("print /D failed: %s %s", result.stdout, result.stderr)
        except (OSError, subprocess.SubprocessError) as exc:
            log.warning("print /D error: %s", exc)

    # Fall back to the system print verb for the default printer
    try:
        os.startfile(path, "print")                            # type: ignore[attr-defined]
        return True, "Sent to the default printer."
    except Exception as exc:                                   # noqa: BLE001
        log.warning("Print verb failed: %s", exc)
        return False, (f"Could not print: {exc}\n"
                       f"The receipt was saved to {path}")


def print_receipt(info: dict, shop_name: str = "AZ Cafe", currency: str = "Rs",
                  printer_name: str = "") -> tuple:
    text = build_receipt_text(info, shop_name=shop_name, currency=currency)
    return print_text(text, printer_name=printer_name)


def save_receipt(info: dict, path: str, shop_name: str = "AZ Cafe",
                 currency: str = "Rs") -> str:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(build_receipt_text(info, shop_name=shop_name, currency=currency))
    return path

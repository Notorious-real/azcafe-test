# ============================================================
#  AZ Cafe - Member CSV import  (Phase 6.5D)
#  Understands two formats:
#
#   1. "AZ Cafe" format  — name, username, password, balance, phone, notes
#   2. Cyber Cafe Pro export — Username, PWORD, Phone, First name, ...
#      (46 columns; the password column is a one-way hash and cannot
#       be recovered, so imported members get a temporary password)
#
#  Pure logic, no Tkinter: unit-testable and usable from the CLI:
#      python -m server.member_import members.csv --dry-run
# ============================================================

import csv
import re
import sys

import database as db

CCP_MARKERS = {"Username", "PWORD", "ACCUMTIME", "GROUP"}
SIMPLE_MARKERS = {"username", "name"}

TEMP_PASSWORD_NOTE = "Imported — password must be reset"


def detect_format(headers: list) -> str:
    """Return 'ccp', 'simple' or 'unknown'."""
    cleaned = {h.strip().lower() for h in headers if h}
    if {"username", "pword"} & cleaned and len(cleaned & {m.lower() for m in CCP_MARKERS}) >= 2:
        return "ccp"
    if {"username"} & cleaned:
        return "simple"
    return "unknown"


def _clean(value) -> str:
    return (value or "").strip()


def _looks_like_junk_row(row: dict, csv_format: str = "simple") -> bool:
    """
    The CCP export we were given has agent transcript lines appended
    below the real data. A real row carries a sane username plus at
    least one piece of account data this software can use — a password
    hash, accumulated minutes or a phone number. Transcript lines have
    none of those, so they are skipped instead of imported.
    """
    populated = sum(1 for v in row.values() if _clean(v))
    if populated < 3:
        return True

    username = _clean(row.get("Username") or row.get("username"))
    if not username or len(username) > 64 or " " in username:
        return True
    lowered = username.lower()
    if lowered.startswith(("#", "'", '"', "{", "\\")):
        return True
    if "step_index" in lowered or "cwd:" in lowered:
        return True

    if csv_format == "ccp":
        pword = _clean(row.get("PWORD"))
        accum = _clean(row.get("ACCUMTIME"))
        phone = _clean(row.get("Phone"))
        hex_hash = bool(re.fullmatch(r"[0-9A-Fa-f]{8,}", pword))
        numeric_minutes = bool(re.fullmatch(r"\d{1,7}", accum))
        phone_digits = len(re.sub(r"\D", "", phone)) >= 10
        if not (hex_hash or numeric_minutes or phone_digits):
            return True
    return False


def _parse_number(value, default=0.0) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def import_csv(path: str, dry_run: bool = False,
               default_password: str = None,
               default_balance: float = None,
               update_existing: bool = False) -> dict:
    """
    Import members from a CSV file. Never raises on bad rows — returns
    a report the UI can show to the operator.
    """
    if default_password is None:
        default_password = db.get_setting("import_default_password", "123456")
    if default_balance is None:
        default_balance = db.get_int_setting("import_default_balance", 0)

    report = {
        "path": path, "format": "unknown", "dry_run": dry_run,
        "added": 0, "updated": 0, "skipped": 0, "entries": [],
        "errors": [], "temp_passwords": 0,
    }

    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            sample = handle.read(4096)
            handle.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(handle, dialect=dialect)
            headers = reader.fieldnames or []
            fmt = detect_format(headers)
            report["format"] = fmt
            if fmt == "unknown":
                report["errors"].append(
                    "Unrecognised CSV headers — needs a 'username' column "
                    "(or a Cyber Cafe Pro export)."
                )
                return report

            rows = list(reader)

    except OSError as exc:
        report["errors"].append(f"Could not read the file: {exc}")
        return report

    for line_no, row in enumerate(rows, start=2):
        if _looks_like_junk_row(row, fmt):
            report["skipped"] += 1
            continue

        try:
            if fmt == "ccp":
                parsed = _parse_ccp_row(row, default_password, default_balance)
            else:
                parsed = _parse_simple_row(row, default_password, default_balance)
        except Exception as exc:                      # noqa: BLE001 - report, don't crash
            report["errors"].append(f"Line {line_no}: {exc}")
            report["skipped"] += 1
            continue

        if parsed is None:
            report["skipped"] += 1
            continue

        if parsed.get("temp_password"):
            report["temp_passwords"] += 1

        existing = db.get_member_by_username(parsed["username"])
        try:
            if existing and update_existing:
                action = "updated"
                if not dry_run:
                    db.update_member(existing["id"], parsed["name"],
                                     parsed["username"], parsed.get("notes", ""),
                                     new_password=None, phone=parsed.get("phone"))
                    if parsed.get("balance"):
                        db.topup_member_balance(existing["id"], parsed["balance"],
                                                "Imported balance adjustment")
                report["updated"] += 1
            elif existing:
                report["skipped"] += 1
                report["entries"].append({"username": parsed["username"],
                                          "action": "skipped (exists)"})
                continue
            else:
                action = "added"
                if not dry_run:
                    db.create_member(parsed["name"], parsed["username"],
                                     parsed["password"], parsed.get("balance", 0.0),
                                     parsed.get("notes", ""), parsed.get("phone", ""))
                report["added"] += 1
        except Exception as exc:                      # noqa: BLE001
            report["errors"].append(f"Line {line_no}: {exc}")
            report["skipped"] += 1
            continue

        report["entries"].append({
            "username": parsed["username"],
            "name": parsed["name"],
            "balance": parsed.get("balance", 0.0),
            "action": action,
        })

    return report


def _parse_simple_row(row: dict, default_password: str, default_balance: float):
    username = _clean(row.get("username"))
    if not username:
        return None
    name = _clean(row.get("name")) or username
    password = _clean(row.get("password")) or default_password
    balance = _parse_number(row.get("balance"), default_balance or 0.0)
    return {
        "name": name,
        "username": username,
        "password": password,
        "balance": balance,
        "phone": _clean(row.get("phone")),
        "notes": _clean(row.get("notes")),
        "temp_password": not _clean(row.get("password")),
    }


def _parse_ccp_row(row: dict, default_password: str, default_balance: float):
    username = _clean(row.get("Username"))
    if not username:
        return None

    deleted = _clean(row.get("Deleted"))
    if deleted in ("1", "-1", "True", "true"):
        return None

    first = _clean(row.get("First name"))
    last = _clean(row.get("Last name"))
    name = " ".join(part for part in (first, last) if part).strip() or username

    phone = _clean(row.get("Phone"))
    notes_bits = []
    if _clean(row.get("Email Address")):
        notes_bits.append(f"email: {_clean(row.get('Email Address'))}")
    accum_time = _clean(row.get("ACCUMTIME"))
    if accum_time:
        notes_bits.append(f"legacy minutes: {accum_time}")
    accum_cost = _clean(row.get("ACCUMCOST"))
    if accum_cost:
        notes_bits.append(f"legacy spend: {accum_cost}")

    return {
        "name": name,
        "username": username,
        # PWORD is an irreversible hash — a temporary password is issued.
        "password": default_password,
        "balance": default_balance or 0.0,
        "phone": phone,
        "notes": " · ".join(notes_bits + [TEMP_PASSWORD_NOTE]),
        "temp_password": True,
    }


def format_report(report: dict) -> str:
    lines = [
        f"File:    {report['path']}",
        f"Format:  {report['format']}",
        f"Added:   {report['added']}",
        f"Updated: {report['updated']}",
        f"Skipped: {report['skipped']}",
    ]
    if report.get("temp_passwords"):
        lines.append(
            f"Temporary passwords issued: {report['temp_passwords']} "
            f"(the source file stores one-way hashes)"
        )
    if report.get("errors"):
        lines.append("")
        lines.append("Problems:")
        lines.extend(f"  • {e}" for e in report["errors"][:15])
    if report.get("dry_run"):
        lines.append("")
        lines.append("Dry run — nothing was written to the database.")
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    dry_run = "--dry-run" in argv
    path = [a for a in argv if not a.startswith("--")][0]
    db.init_db()
    report = import_csv(path, dry_run=dry_run)
    print(format_report(report))
    return 1 if report["errors"] and not report["added"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

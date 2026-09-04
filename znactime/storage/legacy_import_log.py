from __future__ import annotations

import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from znactime.storage.atomic_file import publish_staged_file


def _one_line(value: object) -> str:
    return repr(value).replace("\r", "\\r").replace("\n", "\\n")


def _log_text(database_path, preflight, result, completed_at: datetime) -> str:
    lines = [
        "znacTime legacy CSV import log",
        "",
        "Status: completed",
        f"Completed (UTC): {completed_at.isoformat().replace('+00:00', 'Z')}",
        f"Database: {Path(database_path).resolve()}",
        f"Source: {preflight.source_root}",
        f"Source fingerprint: {preflight.source_fingerprint}",
        f"Manifest digest: {preflight.manifest_digest}",
        "",
        "Outcome",
        f"  Months created: {result.months_created}",
        f"  Months merged: {result.months_merged}",
        f"  Months closed: {result.months_closed}",
        f"  Source-closed months retained as open: {result.closures_kept_open}",
        f"  Days imported: {result.days_imported}",
        f"  Days retaining current SQLite data: {result.days_kept_current}",
        f"  Days unchanged: {result.days_unchanged}",
        f"  Preflight warnings: {result.warning_count}",
        f"  Normalizations: {len(result.normalizations)}",
        "",
        "Preflight issues",
    ]
    if preflight.issues:
        for issue in preflight.issues:
            location = issue.relative_path
            if issue.line is not None:
                location += f":{issue.line}"
            lines.append(f"  [{issue.severity.upper()}] {location}: {issue.message}")
    else:
        lines.append("  None")

    lines.extend(("", "Applied normalizations"))
    if result.normalizations:
        for change in result.normalizations:
            lines.extend(
                (
                    f"  {change.location} | {change.field}",
                    f"    Source: {_one_line(change.source_value)}",
                    f"    Imported: {_one_line(change.imported_value)}",
                    f"    Reason: {change.reason}",
                )
            )
    else:
        lines.append("  None")
    lines.extend(
        (
            "",
            "The source CSV files were read-only import inputs and were not modified.",
            "",
        )
    )
    return "\n".join(lines)


def write_legacy_import_log(database_path, preflight, result) -> Path:
    """Atomically publish one private UTF-8 log for a completed import."""
    completed_at = datetime.now(timezone.utc)
    log_directory = Path(database_path).resolve().parent / "import-logs"
    log_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = completed_at.strftime("%Y%m%dT%H%M%S%fZ")
    target = log_directory / (
        f"legacy-import-{stamp}-{preflight.source_fingerprint[:12]}-"
        f"{uuid.uuid4().hex[:8]}.log"
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=log_directory,
    )
    succeeded = False
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(_log_text(database_path, preflight, result, completed_at))
            stream.flush()
            os.fsync(stream.fileno())
        publish_staged_file(temporary_name, target, overwrite=False)
        succeeded = True
        return target
    finally:
        if not succeeded:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass

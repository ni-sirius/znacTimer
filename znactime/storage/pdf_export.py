from __future__ import annotations

import os
import tempfile
from pathlib import Path

from znactime.storage.atomic_file import (
    publish_staged_file,
    reject_protected_destination,
)


def export_pdf(
    stats,
    output_path,
    *,
    overwrite: bool = False,
    protected_paths=(),
):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    target = Path(output_path)
    protected_paths = tuple(protected_paths)
    reject_protected_destination(target, protected_paths)
    if target.exists() and not overwrite:
        raise FileExistsError(str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(descriptor)
    try:
        pdf = canvas.Canvas(temporary_name, pagesize=A4)
        pdf.drawString(50, 800, "Monthly Time Report")
        pdf.drawString(50, 770, f"Year: {stats.year}")
        pdf.drawString(50, 750, f"Month: {stats.month}")
        pdf.drawString(50, 730, f"Overtime: {stats.overtime:.2f} h")
        pdf.save()
        with open(temporary_name, "r+b") as stream:
            os.fsync(stream.fileno())
        publish_staged_file(
            temporary_name,
            target,
            overwrite=overwrite,
            protected_paths=protected_paths,
        )
    except Exception:
        try:
            Path(temporary_name).unlink()
        except FileNotFoundError:
            pass
        raise

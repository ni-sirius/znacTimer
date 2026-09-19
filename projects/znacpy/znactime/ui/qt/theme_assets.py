import tempfile
from functools import lru_cache
from pathlib import Path

from znactime.ui.qt import (
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    Qt,
)
from znactime.ui.qt.color_scheme import theme_color


_asset_directory = None


def _temporary_asset_directory() -> Path:
    global _asset_directory
    if _asset_directory is None:
        _asset_directory = tempfile.TemporaryDirectory(
            prefix="znactime-theme-"
        )
    return Path(_asset_directory.name)


def _draw_chevron(path: Path, direction: str, color: str):
    pixmap = QPixmap(12, 12)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)

    chevron = QPainterPath()
    if direction == "up":
        chevron.moveTo(2.5, 7.5)
        chevron.lineTo(6.0, 4.0)
        chevron.lineTo(9.5, 7.5)
    else:
        chevron.moveTo(2.5, 4.5)
        chevron.lineTo(6.0, 8.0)
        chevron.lineTo(9.5, 4.5)
    painter.drawPath(chevron)
    painter.end()

    if not pixmap.save(str(path), "PNG"):
        raise RuntimeError(f"Could not create themed asset {path}.")


@lru_cache(maxsize=4)
def themed_chevron_paths(dark: bool, inverted: bool = False):
    directory = _temporary_asset_directory()
    color_property = "on_primary" if inverted else "primary"
    color = theme_color(color_property, dark=dark)
    theme_id = "dark" if dark else "light"
    variant = "on_primary" if inverted else "primary"
    paths = {
        direction: directory / f"chevron_{direction}_{theme_id}_{variant}.png"
        for direction in ("up", "down")
    }
    for direction, path in paths.items():
        _draw_chevron(path, direction, color)
    return paths["up"].as_posix(), paths["down"].as_posix()

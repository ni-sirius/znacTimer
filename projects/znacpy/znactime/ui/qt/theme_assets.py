import tempfile
from functools import lru_cache
from pathlib import Path

from znactime.ui.qt import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRectF,
    Qt,
)
from znactime.ui.qt.color_scheme import theme_color


_asset_directory = None


@lru_cache(maxsize=10)
def themed_workday_icon(action: str, dark: bool):
    icon = QIcon()
    for mode in (QIcon.Mode.Normal, QIcon.Mode.Disabled):
        color_property = (
            "player.disabled_text" if mode == QIcon.Mode.Disabled
            else "player.text" if action == "stop"
            else "on_primary"
        )
        color = QColor(theme_color(color_property, dark=dark))
        pixmap = QPixmap(40, 40)
        pixmap.setDevicePixelRatio(2)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)

        if action in ("start", "resume"):
            triangle = QPainterPath()
            left = 8 if action == "resume" else 6
            triangle.moveTo(left, 4)
            triangle.lineTo(16, 10)
            triangle.lineTo(left, 16)
            triangle.closeSubpath()
            painter.drawPath(triangle)
            if action == "resume":
                painter.drawRoundedRect(QRectF(3, 4, 2.5, 12), 0.7, 0.7)
        elif action == "pause":
            for left in (5, 12):
                painter.drawRoundedRect(QRectF(left, 4, 3, 12), 0.7, 0.7)
        elif action == "stop":
            painter.drawRoundedRect(QRectF(4.5, 4.5, 11, 11), 1, 1)
        elif action == "reopen":
            pen = QPen(color)
            pen.setWidthF(1.8)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            arrow = QPainterPath()
            arrow.moveTo(4, 8)
            arrow.cubicTo(5, 1, 17, 2, 17, 10)
            arrow.cubicTo(17, 18, 7, 19, 4, 14)
            arrow.moveTo(4, 3)
            arrow.lineTo(4, 8)
            arrow.lineTo(9, 8)
            painter.drawPath(arrow)

        painter.end()
        icon.addPixmap(pixmap, mode)
    return icon


@lru_cache(maxsize=4)
def themed_lock_icon(dark: bool, *, closed: bool):
    pixmap = QPixmap(40, 40)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = "tokens.danger_text" if closed else "primary"
    pen = QPen(QColor(theme_color(color, dark=dark)))
    pen.setWidthF(1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    shackle = QPainterPath()
    shackle.moveTo(7, 9)
    if closed:
        shackle.lineTo(7, 6)
        shackle.cubicTo(7, 2, 13, 2, 13, 6)
        shackle.lineTo(13, 9)
    else:
        shackle.lineTo(7, 5)
        shackle.cubicTo(7, 1, 14, 1, 14, 5)
        shackle.lineTo(14, 6)
    painter.drawPath(shackle)
    painter.drawRoundedRect(QRectF(5, 9, 10, 9), 2, 2)
    painter.drawLine(10, 13, 10, 15)
    painter.end()
    return QIcon(pixmap)


@lru_cache(maxsize=2)
def themed_information_icon(dark: bool):
    pixmap = QPixmap(40, 40)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(theme_color("tokens.danger_text", dark=dark))
    pen = QPen(color)
    pen.setWidthF(1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawEllipse(2, 2, 16, 16)
    painter.drawLine(10, 9, 10, 14)
    painter.setBrush(color)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(9, 5, 2, 2)
    painter.end()
    return QIcon(pixmap)


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

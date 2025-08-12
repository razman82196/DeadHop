from __future__ import annotations
from PyQt6.QtCore import Qt, QRect, QSize, QPoint
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPainterPath, QIcon, QFont


def _letter_pixmap(letter: str, size: int, bg: QColor) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    # background circle
    p.setBrush(bg)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(0, 0, size, size)
    # letter
    f = QFont()
    f.setBold(True)
    f.setPointSizeF(size * 0.5)
    p.setFont(f)
    p.setPen(Qt.GlobalColor.white)
    rect = QRect(0, 0, size, size)
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, (letter or '?').upper())
    p.end()
    return pm


def _nick_seed_color(nick: str) -> QColor:
    try:
        s = (nick or '').lower().encode('utf-8')
        h = 0
        for b in s:
            h = (h * 131 + int(b)) & 0xFFFFFFFF
        hue = h % 360
        # pleasant saturation/lightness
        import colorsys
        r, g, b = colorsys.hls_to_rgb(hue/360.0, 0.58, 0.65)
        return QColor(int(r*255), int(g*255), int(b*255))
    except Exception:
        return QColor('#7c7cff')


def _rounded(pix: QPixmap, size: int) -> QPixmap:
    if pix.isNull():
        out = QPixmap(size, size)
        out.fill(Qt.GlobalColor.transparent)
        return out
    scaled = pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    p.setClipPath(path)
    # center-crop draw
    x = (scaled.width() - size) // 2
    y = (scaled.height() - size) // 2
    p.drawPixmap(-x, -y, scaled)
    p.end()
    return out


def make_avatar_icon(nick: str, avatar_path: str | None, size: int = 24, online: bool = False, status: str | None = None) -> QIcon:
    # base avatar
    base_pm: QPixmap
    if avatar_path:
        pm = QPixmap(avatar_path)
        if pm.isNull():
            base_pm = _letter_pixmap(nick[:1] if nick else '?', size, _nick_seed_color(nick))
        else:
            base_pm = _rounded(pm, size)
    else:
        base_pm = _letter_pixmap(nick[:1] if nick else '?', size, _nick_seed_color(nick))
    # overlay presence dot
    dot_d = max(6, int(size * 0.28))
    dot_pm = QPixmap(base_pm)
    p = QPainter(dot_pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    color = QColor('#22cc66') if online else QColor('#9aa0a6')
    p.setBrush(color)
    p.setPen(Qt.PenStyle.NoPen)
    # place at bottom-right with small margin
    m = max(1, int(size * 0.06))
    x = dot_pm.width() - dot_d - m
    y = dot_pm.height() - dot_d - m
    p.drawEllipse(QRect(x, y, dot_d, dot_d))
    # Top-left status badge (~ founder, & admin, @ op, % halfop, + voice)
    if status:
        s = status.strip()[:1]
        badge_map = {
            '~': QColor('#b388ff'),  # founder - violet
            '&': QColor('#ff79c6'),  # admin - pink
            '@': QColor('#ffb74d'),  # op - orange
            '%': QColor('#26c6da'),  # halfop - cyan
            '+': QColor('#64b5f6'),  # voice - blue
        }
        bc = badge_map.get(s)
        if bc is not None:
            bd = max(6, int(size * 0.26))
            bx = m
            by = m
            p.setBrush(bc)
            p.drawEllipse(QRect(bx, by, bd, bd))
    p.end()
    return QIcon(dot_pm)

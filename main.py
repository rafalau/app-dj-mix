#!/usr/bin/env python3
"""
DJ Mix Player
pip install PyQt6 pygame mutagen sounddevice
"""
import sys
import os
import json
import math
import time
import random
import threading
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QListWidget, QListWidgetItem,
    QLineEdit, QComboBox, QFileDialog, QMessageBox, QMenu,
    QTabWidget, QSizePolicy, QFrame, QScrollArea,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QMimeData, QUrl, QPointF, QRectF
from PyQt6.QtGui import (QPainter, QColor, QLinearGradient, QRadialGradient, QFont,
                         QDragEnterEvent, QDropEvent, QPolygonF)

# ── Optional backends ─────────────────────────────────────────────────────────
try:
    import pygame
    pygame.mixer.pre_init(44100, -16, 2, 4096)
    pygame.mixer.init()
    HAS_PYGAME = True
except Exception:
    HAS_PYGAME = False

try:
    import sounddevice as sd
    HAS_SD = True
except Exception:
    HAS_SD = False

try:
    from mutagen import File as MutagenFile
    HAS_MUTAGEN = True
except Exception:
    HAS_MUTAGEN = False

# ── Constants ─────────────────────────────────────────────────────────────────
AUDIO_EXTENSIONS = {'.mp3', '.mpa', '.wav', '.flac', '.ogg', '.aac', '.m4a', '.wma', '.opus', '.mp2', '.mp4'}
FORMATS_FILTER = "Áudio (*.mp3 *.mpa *.wav *.flac *.ogg *.aac *.m4a *.wma *.opus *.mp2 *.mp4);;Todos (*.*)"

C = {
    'bg':        '#111111',
    'panel':     '#1a1a1a',
    'panel2':    '#202020',
    'header':    '#0d0d0d',
    'border':    '#2a2a2a',
    'border2':   '#383838',
    'accent':    '#1464b4',
    'accent2':   '#0d4f9e',
    'accent_lt': '#1878d4',
    'text':      '#ffffff',
    'text_dim':  '#888888',
    'playing':   '#00dd55',
    'hover':     '#1a2a3a',
    'sel':       '#1464b4',
    'vu_green':  '#00bb44',
    'vu_yellow': '#ddaa00',
    'vu_red':    '#dd2222',
}

PANEL_HEADERS = [
    '#002d6b', '#002d6b', '#002d6b',
    '#002d6b', '#002d6b', '#002d6b',
    '#002d6b', '#002d6b', '#002d6b',
]

DATA_FILE = Path.home() / '.djmixplayer' / 'playlists.json'


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_duration(path: str) -> str:
    try:
        if HAS_MUTAGEN:
            f = MutagenFile(path)
            if f and hasattr(f, 'info') and hasattr(f.info, 'length'):
                s = int(f.info.length)
                return f"{s // 60:02d}:{s % 60:02d}"
    except Exception:
        pass
    return '--:--'


def display_name(path: str) -> str:
    name = ''
    if HAS_MUTAGEN:
        try:
            f = MutagenFile(path, easy=True)
            if f:
                title  = f.get('title',  [''])[0]
                artist = f.get('artist', [''])[0]
                if title and artist:
                    name = f"{artist} — {title}"
                elif title:
                    name = title
        except Exception:
            pass
    if not name:
        name = Path(path).stem
    return name.upper()


# ── Audio Engine ──────────────────────────────────────────────────────────────
class AudioEngine(QObject):
    sig_pos     = pyqtSignal(float)   # 0.0–1.0
    sig_state   = pyqtSignal(str)     # playing / paused / stopped
    sig_dur     = pyqtSignal(int)     # seconds
    sig_vu      = pyqtSignal(float, float)
    sig_ended   = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._path      = None
        self._state     = 'stopped'
        self._duration  = 0
        self._t0        = 0.0
        self._offset    = 0.0
        self._volume    = 0.8
        self._vu_l      = 0.0
        self._vu_r      = 0.0
        self._vu_peak_l = 0.0
        self._vu_peak_r = 0.0
        self._peak_hold = 0

        self._tick_timer = QTimer()
        self._tick_timer.setInterval(40)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start()

    # ── public API ─────────────────────────────────────────────────────────
    def load(self, path: str) -> bool:
        self._path = None
        self._duration = 0
        if HAS_PYGAME:
            try:
                pygame.mixer.music.load(path)
                self._path = path
                if HAS_MUTAGEN:
                    f = MutagenFile(path)
                    if f and hasattr(f.info, 'length'):
                        self._duration = int(f.info.length)
                self.sig_dur.emit(self._duration)
                return True
            except Exception as e:
                self.sig_state.emit('stopped')
                raise RuntimeError(str(e))
        return False

    def play(self):
        if not self._path:
            return
        if HAS_PYGAME:
            try:
                if self._state == 'paused':
                    pygame.mixer.music.unpause()
                    self._t0 = time.time()
                else:
                    pygame.mixer.music.play()
                    self._t0 = time.time()
                    self._offset = 0.0
                self._state = 'playing'
                self.sig_state.emit('playing')
            except Exception as e:
                print(f"play error: {e}")
                self._state = 'stopped'
                self.sig_state.emit('stopped')

    def pause(self):
        if HAS_PYGAME and self._state == 'playing':
            pygame.mixer.music.pause()
            self._offset += time.time() - self._t0
            self._state = 'paused'
            self.sig_state.emit('paused')

    def stop(self):
        if HAS_PYGAME:
            pygame.mixer.music.stop()
        self._state = 'stopped'
        self._offset = 0.0
        self.sig_state.emit('stopped')
        self.sig_pos.emit(0.0)

    def seek(self, pos: float):
        if HAS_PYGAME and self._duration > 0 and self._path:
            target = pos * self._duration
            try:
                was_playing = self._state == 'playing'
                pygame.mixer.music.play(start=target)
                self._offset = target
                self._t0 = time.time()
                if not was_playing:
                    pygame.mixer.music.pause()
                    self._state = 'paused'
                else:
                    self._state = 'playing'
            except Exception as e:
                print(f"seek error: {e}")

    def set_volume(self, v: float):
        self._volume = max(0.0, min(1.0, v))
        if HAS_PYGAME:
            pygame.mixer.music.set_volume(self._volume)

    def pos_seconds(self) -> int:
        if self._duration == 0:
            return 0
        return int(self._pos_frac() * self._duration)

    def get_devices(self) -> list:
        if HAS_SD:
            try:
                return [d['name'] for d in sd.query_devices()
                        if d['max_output_channels'] > 0]
            except Exception:
                pass
        return ['Dispositivo padrão']

    # ── internal ───────────────────────────────────────────────────────────
    def _pos_frac(self) -> float:
        if self._duration == 0:
            return 0.0
        if self._state == 'playing':
            elapsed = self._offset + (time.time() - self._t0)
        elif self._state == 'paused':
            elapsed = self._offset
        else:
            return 0.0
        return min(1.0, elapsed / self._duration)

    def _tick(self):
        if self._state == 'playing':
            if HAS_PYGAME and not pygame.mixer.music.get_busy():
                self._state = 'stopped'
                self._offset = 0.0
                self.sig_state.emit('stopped')
                self.sig_ended.emit()
                self._decay_vu()
                return
            self.sig_pos.emit(self._pos_frac())
            self._animate_vu()
        else:
            self._decay_vu()

    def _animate_vu(self):
        t = time.time()
        base = 0.55 + 0.30 * abs(
            0.5 * (1 + __import__('math').sin(t * 4.1)) *
            (0.7 + 0.3 * __import__('math').sin(t * 7.3))
        )
        self._vu_l = max(0.0, min(1.0, base + random.gauss(0, 0.07)))
        self._vu_r = max(0.0, min(1.0, base + random.gauss(0, 0.07)))
        self.sig_vu.emit(self._vu_l, self._vu_r)

    def _decay_vu(self):
        if self._vu_l > 0.001 or self._vu_r > 0.001:
            self._vu_l *= 0.82
            self._vu_r *= 0.82
            self.sig_vu.emit(self._vu_l, self._vu_r)

    @property
    def state(self): return self._state
    @property
    def duration(self): return self._duration


# ── VU Meter Analógico ────────────────────────────────────────────────────────
class VUMeter(QWidget):
    """
    Arco CCW de 180° (esq/9h) até 360°/0° (dir/3h) passando pelo topo (270°).
    Nível 0 = agulha à esquerda, nível 1 = agulha à direita.
    Convenção de ângulos Qt: 0°=3h, CCW positivo, 270°=12h(topo).
    Convenção do ponteiro: ângulo padrão = 180 - nível*180, Y invertido.
    """
    def __init__(self, ch='L', parent=None):
        super().__init__(parent)
        self.ch    = ch
        self._lvl  = 0.0
        self._peak = 0.0
        self._hold = 0
        self.setMinimumSize(140, 120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_level(self, v: float):
        self._lvl = max(0.0, min(1.0, v))
        if self._lvl > self._peak:
            self._peak = self._lvl
            self._hold = 25
        else:
            if self._hold > 0:
                self._hold -= 1
            else:
                self._peak = max(0.0, self._peak - 0.012)
        self.update()

    def paintEvent(self, _):
        from PyQt6.QtGui import QPen

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        p.fillRect(0, 0, w, h, QColor(C['bg']))

        margin = 8
        cx = w / 2.0
        cy = float(h - margin)
        # r + ARC_W deve caber dentro de cx; com ARC_W ≈ r/5 → r ≤ (cx-2)*5/6
        r     = int(min((cx - 2) * 5.0 / 6.0, cy - 4))
        ARC_W = max(6, r // 5)
        r_mid = r - ARC_W // 2

        # Face do medidor
        cxi, cyi = int(cx), int(cy)
        p.setPen(QPen(QColor('#2a2a2a'), 2))
        p.setBrush(QColor('#111820'))
        p.drawEllipse(cxi - r - ARC_W, cyi - r - ARC_W,
                      (r + ARC_W) * 2, (r + ARC_W) * 2)

        # ── helper: desenha arco em convenção Qt ──────────────────────────
        # start_deg e span_deg em graus Qt (CCW a partir de 3h)
        def arc(start_deg, span_deg, color, alpha=255):
            col = QColor(color); col.setAlpha(alpha)
            p.setPen(QPen(col, ARC_W, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            p.drawArc(cxi - r_mid, cyi - r_mid, r_mid * 2, r_mid * 2,
                      int(start_deg * 16), int(span_deg * 16))

        # ── Zonas de fundo (escala 0-100-140) ────────────────────────────
        # Verde: 0→100  = 100/140 × 180° = 128.6° ≈ 129°
        # Amarelo: 100→120 = 20/140 × 180° = 25.7° ≈ 26°
        # Vermelho: 120→140 = 20/140 × 180° = 25.4° ≈ 25°
        G_SPAN, Y_SPAN, R_SPAN = 129, 26, 25  # total = 180°
        arc(180,             G_SPAN, C['vu_green'],  55)
        arc(180 + G_SPAN,    Y_SPAN, C['vu_yellow'], 55)
        arc(180 + G_SPAN + Y_SPAN, R_SPAN, C['vu_red'], 55)

        # ── Zonas preenchidas até o nível atual ───────────────────────────
        sweep = self._lvl * 180
        g_fill = min(sweep, G_SPAN)
        if g_fill > 0:
            arc(180, g_fill, C['vu_green'], 255)
            sweep -= g_fill
        y_fill = min(sweep, Y_SPAN)
        if y_fill > 0:
            arc(180 + G_SPAN, y_fill, C['vu_yellow'], 255)
            sweep -= y_fill
        r_fill = min(sweep, R_SPAN)
        if r_fill > 0:
            arc(180 + G_SPAN + Y_SPAN, r_fill, C['vu_red'], 255)

        # ── Marcações e números (escala 0, 20, 40, 60, 80, 100, 120, 140) ─
        SCALE_MAX = 140
        ticks = [(v, v % 40 == 0 or v == 100) for v in range(0, 141, 20)]
        for val, major in ticks:
            pct = val / SCALE_MAX
            a  = math.radians(180 - pct * 180)
            ca, sa = math.cos(a), math.sin(a)
            tick_len = 9 if major else 5
            ri = r - ARC_W - 1
            x1 = cxi + int(ri * ca);            y1 = cyi - int(ri * sa)
            x2 = cxi + int((ri - tick_len) * ca); y2 = cyi - int((ri - tick_len) * sa)
            p.setPen(QPen(QColor('#666666' if major else '#404040'), 1))
            p.drawLine(x1, y1, x2, y2)
            if major:
                # Labels fora do arco (entre arco e borda do widget)
                outer_r = r + ARC_W // 2 + 3
                lbl_r   = min(outer_r, int(cx) - 13)
                lx = cxi + int(lbl_r * ca) - 10
                # levanta labels horizontais para não colarem na borda inferior
                lift = int((1.0 - abs(sa)) * 9)
                ly = cyi - int(lbl_r * sa) - 7 - lift
                p.setPen(QColor('#aaaaaa' if val != 100 else '#ddaa00'))
                p.setFont(QFont('Ubuntu', max(5, r // 12), QFont.Weight.Bold))
                p.drawText(lx, ly, 20, 14, Qt.AlignmentFlag.AlignCenter, str(val))

        # ── Peak hold ─────────────────────────────────────────────────────
        if self._peak > 0.02:
            pa = math.radians(180 - self._peak * 180)
            pk_c = (C['vu_red'] if self._peak > 0.85 else
                    C['vu_yellow'] if self._peak > 0.65 else C['vu_green'])
            p.setPen(QPen(QColor(pk_c), 2))
            px1 = cxi + int((r - ARC_W - 2) * math.cos(pa))
            py1 = cyi - int((r - ARC_W - 2) * math.sin(pa))
            px2 = cxi + int((r - ARC_W - 12) * math.cos(pa))
            py2 = cyi - int((r - ARC_W - 12) * math.sin(pa))
            p.drawLine(px1, py1, px2, py2)

        # ── Agulha principal ──────────────────────────────────────────────
        na = math.radians(180 - self._lvl * 180)
        nx = cxi + int((r - ARC_W - 4) * math.cos(na))
        ny = cyi - int((r - ARC_W - 4) * math.sin(na))
        p.setPen(QPen(QColor('white'), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(cxi, cyi, nx, ny)

        # Hub
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#cccccc'))
        p.drawEllipse(cxi - 4, cyi - 4, 8, 8)

        # Label
        p.setPen(QColor('#aaaaaa'))
        p.setFont(QFont('Ubuntu', 8, QFont.Weight.Bold))
        p.drawText(0, cyi - r // 2, w, r // 2,
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   self.ch)
        p.end()


# ── Digital VU Bar (segmentos verticais) ─────────────────────────────────────
class DigitalVUBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._lvl  = 0.0
        self._peak = 0.0
        self._hold = 0
        self.setFixedWidth(16)
        self.setMinimumHeight(80)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

    def set_level(self, v: float):
        self._lvl = max(0.0, min(1.0, v))
        if self._lvl > self._peak:
            self._peak = self._lvl
            self._hold = 28
        else:
            if self._hold > 0:
                self._hold -= 1
            else:
                self._peak = max(0.0, self._peak - 0.010)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(C['bg']))

        SEG, GAP = 3, 1
        STEP  = SEG + GAP
        total = max(1, h // STEP)
        lit   = int(self._lvl * total)

        for i in range(total):
            pct = i / total
            color = (C['vu_red'] if pct >= 0.85 else
                     C['vu_yellow'] if pct >= 0.65 else C['vu_green'])
            y = h - (i + 1) * STEP
            if i < lit:
                p.fillRect(1, y, w - 2, SEG, QColor(color))
            else:
                dim = QColor(color); dim.setAlpha(30)
                p.fillRect(1, y, w - 2, SEG, dim)

        if self._peak > 0.02:
            pk_i = min(int(self._peak * total), total - 1)
            pk_y = h - (pk_i + 1) * STEP
            pk_c = (C['vu_red'] if self._peak >= 0.85 else
                    C['vu_yellow'] if self._peak >= 0.65 else C['vu_green'])
            p.fillRect(1, pk_y, w - 2, SEG, QColor(pk_c))
        p.end()


# ── Delegate: garante cor verde na música tocando em qualquer estado ──────────
from PyQt6.QtWidgets import QStyledItemDelegate, QStyle
from PyQt6.QtGui import QColor

class SongDelegate(QStyledItemDelegate):
    PLAYING_ROLE = Qt.ItemDataRole.UserRole + 2

    def paint(self, painter, option, index):
        playing = index.data(self.PLAYING_ROLE)
        if playing:
            painter.save()
            # Fundo verde-escuro sempre, independente de seleção/foco
            painter.fillRect(option.rect, QColor('#0a2a14'))
            # Texto verde
            painter.setPen(QColor('#00dd55'))
            font = option.font
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(
                option.rect.adjusted(8, 0, -4, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                index.data(Qt.ItemDataRole.DisplayRole) or ''
            )
            painter.restore()
        else:
            super().paint(painter, option, index)


# ── Playlist List ─────────────────────────────────────────────────────────────
class PlaylistList(QListWidget):
    pass


# ── Playlist Panel ────────────────────────────────────────────────────────────
class SongItem(QListWidgetItem):
    _PATH_ROLE   = Qt.ItemDataRole.UserRole
    _NAME_ROLE   = Qt.ItemDataRole.UserRole + 1
    _PLAYING_ROLE = Qt.ItemDataRole.UserRole + 2

    def __init__(self, path: str):
        super().__init__()
        name = display_name(path)
        self.setData(self._PATH_ROLE, path)
        self.setData(self._NAME_ROLE, name)
        self.setText(f"  {name}")
        self.setToolTip(path)

    @property
    def path(self) -> str:
        return self.data(self._PATH_ROLE)

    def matches(self, q: str) -> bool:
        name = self.data(self._NAME_ROLE)
        return q in name.lower() or q in Path(self.path).name.lower()


class PlaylistPanel(QWidget):
    sig_play = pyqtSignal(str)

    def __init__(self, name: str, color: str, parent=None):
        super().__init__(parent)
        self._name   = name
        self._color  = color
        self._songs: list[str] = []
        self.setAcceptDrops(True)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── header bar ───────────────────────────────────────────────────
        hdr = QWidget()
        self._hdr = hdr
        hdr.setFixedHeight(30)
        hdr.setStyleSheet(f"background:{self._color}; border-radius:5px 5px 0 0;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(8, 0, 4, 0)
        hl.setSpacing(3)

        self._lbl = QLabel(self._name.upper())
        self._lbl.setStyleSheet("color:white; font-weight:bold; font-size:13px; font-family:'Ubuntu','DejaVu Sans','Arial',sans-serif; letter-spacing:1px;")
        self._lbl.mouseDoubleClickEvent = lambda _: self._rename()
        self._lbl.setCursor(Qt.CursorShape.IBeamCursor)
        self._lbl.setToolTip('Duplo clique para renomear')
        hl.addWidget(self._lbl)
        hl.addStretch()

        for text, tip, fn in [
            ('✎', 'Renomear playlist',  self._rename),
            ('+', 'Adicionar músicas',  self._add_files),
            ('⊕', 'Adicionar pasta',    self._add_folder),
            ('✕', 'Limpar playlist',    self._clear),
        ]:
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setFixedSize(20, 20)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setStyleSheet("""
                QPushButton{background:rgba(255,255,255,.12);color:white;border:none;
                             border-radius:3px;font-size:11px;}
                QPushButton:hover{background:rgba(255,255,255,.28);}
            """)
            b.clicked.connect(fn)
            hl.addWidget(b)

        layout.addWidget(hdr)

        # ── sub-header: count ─────────────────────────────────────────────
        self._count = QLabel("  0 músicas")
        self._count.setFixedHeight(16)
        self._count.setStyleSheet(
            f"background:{self._darker(self._color)};"
            f"color:rgba(255,255,255,.5);font-size:9px;padding-left:6px;"
        )
        layout.addWidget(self._count)

        # ── song list ─────────────────────────────────────────────────────
        self._list = PlaylistList()
        self._list.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._list.setFont(QFont('Ubuntu', 13, QFont.Weight.Bold))
        self._list.setItemDelegate(SongDelegate())
        self._apply_list_style(active=False)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._ctx)
        self._list.itemDoubleClicked.connect(lambda i: self.sig_play.emit(i.path))
        self._list.keyPressEvent = self._list_key_press
        layout.addWidget(self._list)

    def _apply_list_style(self, active: bool):
        if active:
            bg_color     = '#0d3a7a'
            border_color = '#1565c0'
            text_color   = '#ffffff'
            sel_color    = '#1976d2'
            hover_color  = '#1565c0'
            item_border  = 'rgba(255,255,255,.12)'
            scroll_bg    = '#0a2a5e'
            scroll_hdl   = '#1878d4'
        else:
            bg_color     = '#111827'
            border_color = '#1e3a5f'
            text_color   = '#d1d5db'
            sel_color    = '#1e3a5f'
            hover_color  = '#1a2d47'
            item_border  = 'rgba(255,255,255,.06)'
            scroll_bg    = '#0d1525'
            scroll_hdl   = '#1464b4'

        self._list.setStyleSheet(f"""
            QListWidget{{
                background:{bg_color};
                border:1px solid {border_color};
                border-top:none;
                border-radius:0 0 3px 3px;
                color:{text_color};
                font-family:'Ubuntu','DejaVu Sans','Arial',sans-serif;
                font-size:13px;
                font-weight:bold;
                outline:none;
            }}
            QListWidget::item{{
                height:22px;
                padding-left:4px;
                border-bottom:1px solid {item_border};
            }}
            QListWidget::item:selected{{background:{sel_color};}}
            QListWidget::item:selected:active{{background:{sel_color};}}
            QListWidget::item:hover{{background:{hover_color};}}
            QListWidget::item:focus{{outline:none;}}
            QScrollBar:vertical{{
                background:{scroll_bg};
                width:12px;
                border-radius:4px;
                margin:2px;
            }}
            QScrollBar::handle:vertical{{
                background:{scroll_hdl};
                border-radius:4px;
                min-height:24px;
            }}
            QScrollBar::handle:vertical:hover{{
                background:#1e90ff;
            }}
            QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}
        """)

    def set_active(self, active: bool):
        self._apply_list_style(active)
        hdr_bg = '#1565c0' if active else self._color
        self._hdr.setStyleSheet(
            f"background:{hdr_bg};border-radius:3px 3px 0 0;"
        )
        self._list.update()
        self._hdr.update()

    def _list_key_press(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self._list.currentItem()
            if item:
                self.sig_play.emit(item.path)
        else:
            PlaylistList.keyPressEvent(self._list, event)

    # ── drag & drop ───────────────────────────────────────────────────────
    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if Path(p).suffix.lower() in AUDIO_EXTENSIONS:
                self.add_song(p)
            elif os.path.isdir(p):
                self._add_dir(p)
        e.acceptProposedAction()

    # ── actions ───────────────────────────────────────────────────────────
    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Adicionar músicas', '', FORMATS_FILTER)
        for p in paths:
            self.add_song(p)

    def _add_folder(self):
        d = QFileDialog.getExistingDirectory(self, 'Selecionar pasta')
        if d:
            self._add_dir(d)

    def _add_dir(self, folder: str):
        for root, _, files in os.walk(folder):
            for f in sorted(files):
                if Path(f).suffix.lower() in AUDIO_EXTENSIONS:
                    self.add_song(os.path.join(root, f))

    def _rename(self):
        from PyQt6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self, 'Renomear playlist', 'Novo nome:',
            text=self._name
        )
        if ok and new_name.strip():
            self._name = new_name.strip().upper()
            self._lbl.setText(self._name)

    def _clear(self):
        if QMessageBox.question(
            self, 'Limpar', f'Limpar "{self._name}"?'
        ) == QMessageBox.StandardButton.Yes:
            self._list.clear()
            self._songs.clear()
            self._upd_count()

    def _ctx(self, pos):
        item = self._list.itemAt(pos)
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu{{background:{C['panel2']};border:1px solid {C['border2']};
                   color:{C['text']};padding:4px;}}
            QMenu::item{{padding:5px 18px;border-radius:3px;}}
            QMenu::item:selected{{background:{C['sel']};}}
        """)
        if item:
            a_play   = menu.addAction('▶  Reproduzir')
            menu.addSeparator()
            a_rename = menu.addAction('✎  Renomear playlist')
            menu.addSeparator()
            a_remove = menu.addAction('✕  Remover da lista')
            action = menu.exec(self._list.mapToGlobal(pos))
            if action == a_play:
                self.sig_play.emit(item.path)
            elif action == a_rename:
                self._rename()
            elif action == a_remove:
                self._songs.remove(item.path)
                self._list.takeItem(self._list.row(item))
                self._upd_count()
        else:
            a1 = menu.addAction('＋  Adicionar músicas')
            a2 = menu.addAction('⊕  Adicionar pasta')
            a3 = menu.addAction('✎  Renomear playlist')
            action = menu.exec(self._list.mapToGlobal(pos))
            if action == a1: self._add_files()
            elif action == a2: self._add_folder()
            elif action == a3: self._rename()

    # ── public ────────────────────────────────────────────────────────────
    def add_song(self, path: str):
        if path not in self._songs:
            self._songs.append(path)
            self._list.addItem(SongItem(path))
            self._upd_count()

    def filter(self, q: str):
        q = q.lower()
        for i in range(self._list.count()):
            it = self._list.item(i)
            it.setHidden(bool(q) and not it.matches(q))

    def set_playing(self, path: str | None):
        has_playing = False
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it.path == path:
                it.setData(SongItem._PLAYING_ROLE, True)
                has_playing = True
            else:
                it.setData(SongItem._PLAYING_ROLE, False)
        self.set_active(has_playing)

    def to_dict(self)  -> dict: return {'name': self._name, 'songs': self._songs}
    def from_dict(self, d: dict):
        self._name = d.get('name', self._name)
        self._lbl.setText(self._name)
        for p in d.get('songs', []):
            if os.path.exists(p):
                self.add_song(p)

    def _upd_count(self):
        n = self._list.count()
        self._count.setText(f"  {n} música{'s' if n != 1 else ''}")

    @staticmethod
    def _darker(hex_col: str) -> str:
        return QColor(hex_col).darker(140).name()


# ── Tab Page (3×2 grid) ───────────────────────────────────────────────────────
class TabPage(QWidget):
    sig_play = pyqtSignal(str)
    COLS, ROWS = 3, 3

    def __init__(self, idx: int, parent=None):
        super().__init__(parent)
        self._panels: list[PlaylistPanel] = []
        self._idx = idx
        self._build()

    def _build(self):
        g = QGridLayout(self)
        g.setSpacing(7)
        g.setContentsMargins(8, 8, 8, 8)
        for i in range(self.ROWS * self.COLS):
            r, c = divmod(i, self.COLS)
            panel = PlaylistPanel(
                f"PLAYLIST {i + 1 + self._idx * self.ROWS * self.COLS}",
                PANEL_HEADERS[i % len(PANEL_HEADERS)]
            )
            panel.sig_play.connect(self.sig_play)
            self._panels.append(panel)
            g.addWidget(panel, r, c)
        for c in range(self.COLS):  g.setColumnStretch(c, 1)
        for r in range(self.ROWS):  g.setRowStretch(r, 1)

        # Tab navega entre as listas das playlists em ordem
        lists = [p._list for p in self._panels]
        for i in range(len(lists) - 1):
            QWidget.setTabOrder(lists[i], lists[i + 1])
        QWidget.setTabOrder(lists[-1], lists[0])  # circular

    def get_panels(self) -> list: return self._panels

    def filter(self, q: str):
        for p in self._panels: p.filter(q)

    def set_playing(self, path: str | None):
        for p in self._panels: p.set_playing(path)

    def to_dict(self) -> list:   return [p.to_dict() for p in self._panels]
    def from_dict(self, data: list):
        for i, d in enumerate(data[:len(self._panels)]):
            self._panels[i].from_dict(d)


# ── Transport Button (custom painted) ────────────────────────────────────────
class TransportButton(QWidget):
    """
    Botão circular com ícone geométrico desenhado via QPainter.
    icon: 'play' | 'stop' | 'pause' | 'prev' | 'next'
    """
    clicked = pyqtSignal()

    def __init__(self, icon: str, size: int = 60, accent: bool = False, parent=None):
        super().__init__(parent)
        self._icon    = icon
        self._accent  = accent
        self._hovered = False
        self._pressed = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h   = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        r      = min(w, h) / 2.0 - 3.0
        if self._pressed:
            r -= 1.5

        # --- glow externo ---
        if self._hovered:
            gc = QColor(C['accent_lt'] if self._accent else '#3a4a6a')
            for i in range(7, 0, -1):
                gc.setAlpha(i * 9)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(gc)
                ri = r + i
                p.drawEllipse(QRectF(cx - ri, cy - ri, ri * 2, ri * 2))

        # --- fundo do círculo ---
        p.setPen(Qt.PenStyle.NoPen)
        if self._accent:
            grad = QRadialGradient(cx, cy - r * 0.35, r * 1.3)
            grad.setColorAt(0.0, QColor('#6ab0ff'))
            grad.setColorAt(0.45, QColor(C['accent']))
            grad.setColorAt(1.0, QColor(C['accent2']))
        else:
            grad = QRadialGradient(cx, cy - r * 0.35, r * 1.3)
            grad.setColorAt(0.0, QColor('#2e3f5e'))
            grad.setColorAt(1.0, QColor('#111820'))
        p.setBrush(grad)
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # --- borda ---
        ring_color = QColor(C['accent_lt'] if self._accent else C['border2'])
        if self._hovered:
            ring_color = QColor(C['accent_lt'])
        p.setPen(ring_color)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # --- ícone geométrico ---
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('white'))

        if self._icon == 'play':
            # Triângulo apontando para direita com centróide em (cx, cy)
            s = r * 0.38
            w_ = s * 1.8           # largura do triângulo
            x0 = cx - w_ / 3.0    # base deslocada para centróide ficar em cx
            tri = QPolygonF([
                QPointF(x0,        cy - s),
                QPointF(x0,        cy + s),
                QPointF(x0 + w_,   cy),
            ])
            p.drawPolygon(tri)

        elif self._icon == 'stop':
            s = r * 0.33
            p.drawRect(QRectF(cx - s, cy - s, s * 2, s * 2))

        elif self._icon == 'pause':
            bw = r * 0.18
            bh = r * 0.48
            gap = r * 0.14
            p.drawRect(QRectF(cx - gap - bw, cy - bh, bw, bh * 2))
            p.drawRect(QRectF(cx + gap,       cy - bh, bw, bh * 2))

        elif self._icon == 'prev':
            # Barra vertical + triângulo apontando para esquerda
            s  = r * 0.28
            bw = r * 0.13
            gap = r * 0.06
            bar_x = cx - s * 1.1 - bw / 2 - gap
            p.drawRect(QRectF(bar_x, cy - s, bw, s * 2))
            w_ = s * 1.5
            x0 = bar_x + bw + gap * 2
            tri = QPolygonF([
                QPointF(x0 + w_,  cy - s),
                QPointF(x0 + w_,  cy + s),
                QPointF(x0,       cy),
            ])
            p.drawPolygon(tri)

        elif self._icon == 'next':
            # Triângulo apontando para direita + barra vertical
            s  = r * 0.28
            bw = r * 0.13
            gap = r * 0.06
            w_ = s * 1.5
            x0 = cx - w_ / 3.0 - gap
            tri = QPolygonF([
                QPointF(x0,        cy - s),
                QPointF(x0,        cy + s),
                QPointF(x0 + w_,   cy),
            ])
            p.drawPolygon(tri)
            bar_x = x0 + w_ + gap * 2
            p.drawRect(QRectF(bar_x - bw / 2, cy - s, bw, s * 2))

        p.end()

    def set_icon(self, icon: str):
        self._icon = icon
        self.update()

    def enterEvent(self, _):  self._hovered = True;  self.update()
    def leaveEvent(self, _):  self._hovered = False; self.update()
    def mousePressEvent(self, _):   self._pressed = True;  self.update()
    def mouseReleaseEvent(self, e):
        self._pressed = False
        self.update()
        if self.rect().contains(e.position().toPoint()):
            self.clicked.emit()


# ── Seek Bar ──────────────────────────────────────────────────────────────────
class SeekBar(QWidget):
    seeked = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pos  = 0.0
        self._drag = False
        self.setFixedHeight(18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_pos(self, v: float):
        if not self._drag:
            self._pos = v
            self.update()

    def paintEvent(self, _):
        p  = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cy = h // 2

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C['border2']))
        p.drawRoundedRect(0, cy - 2, w, 4, 2, 2)

        fill = int(self._pos * w)
        if fill > 4:
            g = QLinearGradient(0, 0, fill, 0)
            g.setColorAt(0, QColor(C['accent2']))
            g.setColorAt(1, QColor(C['accent_lt']))
            p.setBrush(g)
            p.drawRoundedRect(0, cy - 2, fill, 4, 2, 2)

        kx = max(6, min(w - 6, int(self._pos * w)))
        p.setBrush(QColor('white'))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(kx - 6, cy - 6, 12, 12)
        p.end()

    def _frac(self, e) -> float:
        return max(0.0, min(1.0, e.position().x() / self.width()))

    def mousePressEvent(self,  e): self._drag = True;  self._pos = self._frac(e); self.update()
    def mouseMoveEvent(self,   e):
        if self._drag: self._pos = self._frac(e); self.update()
    def mouseReleaseEvent(self,e): self._drag = False; self._pos = self._frac(e); self.seeked.emit(self._pos); self.update()


# ── Volume Slider (custom drawn — sem artefatos de plataforma) ────────────────
class VolumeSlider(QWidget):
    changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._val  = 0.8
        self._drag = False
        self.setFixedWidth(140)
        self.setFixedHeight(18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_value(self, v: float):
        self._val = max(0.0, min(1.0, v))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cy = h // 2

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C['border2']))
        p.drawRoundedRect(0, cy - 2, w, 4, 2, 2)

        fill = int(self._val * w)
        if fill > 4:
            g = QLinearGradient(0, 0, fill, 0)
            g.setColorAt(0, QColor(C['accent2']))
            g.setColorAt(1, QColor(C['accent_lt']))
            p.setBrush(g)
            p.drawRoundedRect(0, cy - 2, fill, 4, 2, 2)

        kx = max(6, min(w - 6, int(self._val * w)))
        p.setBrush(QColor('white'))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(kx - 6, cy - 6, 12, 12)
        p.end()

    def _frac(self, e) -> float:
        return max(0.0, min(1.0, e.position().x() / self.width()))

    def mousePressEvent(self,  e): self._drag = True;  self._val = self._frac(e); self.update(); self.changed.emit(self._val)
    def mouseMoveEvent(self,   e):
        if self._drag: self._val = self._frac(e); self.update(); self.changed.emit(self._val)
    def mouseReleaseEvent(self,e): self._drag = False; self._val = self._frac(e); self.update(); self.changed.emit(self._val)


# ── Transport Bar ─────────────────────────────────────────────────────────────
class TransportBar(QWidget):
    sig_play   = pyqtSignal()
    sig_pause  = pyqtSignal()
    sig_stop   = pyqtSignal()
    sig_prev   = pyqtSignal()
    sig_next   = pyqtSignal()
    sig_seek   = pyqtSignal(float)
    sig_volume = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dur   = 0
        self._state = 'stopped'
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 4, 16, 4)
        root.setSpacing(3)

        # ── Linha 1: tempo (esq) | nome da música (centro) ──────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(0)
        top_row.setContentsMargins(0, 0, 0, 0)

        time_col = QVBoxLayout()
        time_col.setSpacing(0)
        self._elapsed = QLabel('00:00')
        self._elapsed.setStyleSheet(
            f"color:{C['text']};font-family:'Courier New',Courier;"
            f"font-size:24px;font-weight:bold;letter-spacing:3px;"
        )
        self._total = QLabel('00:00')
        self._total.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._total.setStyleSheet(
            f"color:{C['text_dim']};font-family:'Courier New',Courier;"
            f"font-size:11px;letter-spacing:1px;"
        )
        time_col.addStretch()
        time_col.addWidget(self._elapsed)
        time_col.addWidget(self._total)
        time_col.addStretch()
        top_row.addLayout(time_col)

        self._title = QLabel('Nenhuma música selecionada')
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setStyleSheet(
            f"color:{C['text_dim']};font-size:12px;font-weight:500;"
            "letter-spacing:0.5px;"
        )
        top_row.addWidget(self._title, 1)
        root.addLayout(top_row)

        # ── Linha 2: seek bar largura total ──────────────────────────────
        self._seek = SeekBar()
        self._seek.seeked.connect(self.sig_seek)
        root.addWidget(self._seek)

        # ── Linha 3: botões + volume lado a lado ─────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.setContentsMargins(0, 2, 0, 0)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._btn_prev      = TransportButton('prev', size=40, accent=False)
        self._btn_stop      = TransportButton('stop', size=44, accent=False)
        self._btn_playpause = TransportButton('play', size=64, accent=True)
        self._btn_next      = TransportButton('next', size=40, accent=False)

        for _b in (self._btn_prev, self._btn_stop, self._btn_playpause, self._btn_next):
            _b.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._btn_prev     .clicked.connect(self.sig_prev)
        self._btn_stop     .clicked.connect(self._on_stop)
        self._btn_playpause.clicked.connect(self._toggle)
        self._btn_next     .clicked.connect(self.sig_next)

        btn_row.addStretch(1)
        btn_row.addWidget(self._btn_prev)
        btn_row.addWidget(self._btn_stop)
        btn_row.addWidget(self._btn_playpause)
        btn_row.addWidget(self._btn_next)
        btn_row.addStretch(1)

        # Volume ao lado direito dos botões
        vlbl = QLabel('VOLUME')
        vlbl.setStyleSheet(
            f"color:{C['text_dim']};font-size:9px;letter-spacing:2px;font-weight:bold;")
        vlbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vlbl.setContentsMargins(0, 5, 0, 0)
        self._vol = VolumeSlider()
        self._vol.set_value(0.8)
        self._vol.changed.connect(self.sig_volume)

        vol_col = QVBoxLayout()
        vol_col.setSpacing(4)
        vol_col.setContentsMargins(0, 0, 0, 0)
        vol_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        vol_col.addWidget(vlbl)
        vol_col.addWidget(self._vol)
        btn_row.addLayout(vol_col)

        root.addLayout(btn_row)

    # ── internos ──────────────────────────────────────────────────────────
    def _toggle(self):
        if self._state == 'playing':
            self.sig_pause.emit()
        else:
            self.sig_play.emit()

    def _on_stop(self):
        self.sig_stop.emit()

    # ── public ────────────────────────────────────────────────────────────
    def set_song(self, name: str):
        metrics = self._title.fontMetrics()
        elided  = metrics.elidedText(name, Qt.TextElideMode.ElideMiddle, 400)
        self._title.setText(elided)
        self._title.setToolTip(name)

    def set_pos(self, frac: float, elapsed: int):
        self._seek.set_pos(frac)
        m, s = elapsed // 60, elapsed % 60
        self._elapsed.setText(f"{m:02d}:{s:02d}")

    def set_duration(self, secs: int):
        self._dur = secs
        m, s = secs // 60, secs % 60
        self._total.setText(f"{m:02d}:{s:02d}")

    def set_state(self, state: str):
        self._state = state
        if state == 'playing':
            self._btn_playpause.set_icon('pause')
        else:
            self._btn_playpause.set_icon('play')
        if state == 'stopped':
            self._seek.set_pos(0.0)
            self._elapsed.setText('00:00')


# ── Main Window ───────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._engine        = AudioEngine()
        self._current: str | None = None
        self._pages:   list[TabPage] = []
        self._cur_panel     = None   # PlaylistPanel com a música atual
        self._cur_row       = -1     # índice da música atual no painel
        self._build()
        self._wire()
        self._load()
        self.setWindowTitle('DJ Mix Player')
        self.resize(1280, 820)
        self.setMinimumSize(900, 600)
        QTimer.singleShot(300, self._refresh_panel_styles)

    # ── UI construction ───────────────────────────────────────────────────
    def _build(self):
        self.setStyleSheet(f"""
            QMainWindow{{
                background:{C['bg']};
            }}
            QWidget{{
                color:{C['text']};
                font-family:'Ubuntu','DejaVu Sans','Arial',sans-serif;
                font-size:9px;
                font-weight:bold;
            }}
            QTabWidget::pane{{border:none;background:{C['bg']};}}
            QTabBar::tab{{
                background:{C['panel']};
                color:{C['text_dim']};
                padding:5px 18px;
                margin-right:2px;
                border-radius:3px 3px 0 0;
                font-weight:bold;font-size:11px;letter-spacing:1px;
            }}
            QTabBar::tab:selected{{
                background:{C['header']};
                color:{C['accent_lt']};
                border-bottom:2px solid {C['accent_lt']};
            }}
            QTabBar::tab:hover:!selected{{
                background:{C['hover']};
                color:{C['text']};
            }}
            QDialog, QMessageBox, QInputDialog{{
                background:{C['header']};
                color:{C['text']};
                font-family:'Ubuntu','DejaVu Sans','Arial',sans-serif;
                font-size:15px;
                font-weight:bold;
            }}
            QDialog QLabel, QMessageBox QLabel, QInputDialog QLabel{{
                color:{C['text']};
                font-size:15px;
                font-weight:bold;
            }}
            QDialog QLineEdit, QInputDialog QLineEdit{{
                background:{C['panel']};
                color:{C['text']};
                border:1px solid {C['border2']};
                border-radius:4px;
                padding:6px 10px;
                font-size:15px;
                font-weight:bold;
            }}
            QDialog QPushButton, QMessageBox QPushButton, QInputDialog QPushButton{{
                background:{C['accent']};
                color:white;
                border:none;
                border-radius:5px;
                padding:8px 24px;
                font-size:14px;
                font-weight:bold;
                min-width:80px;
            }}
            QDialog QPushButton:hover, QMessageBox QPushButton:hover, QInputDialog QPushButton:hover{{
                background:{C['accent_lt']};
            }}
            QToolTip{{
                color: #ffffff;
                background-color: #0d1e3a;
                border: 1px solid {C['accent']};
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }}
        """)

        cw = QWidget()
        self.setCentralWidget(cw)
        root = QVBoxLayout(cw)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── top bar ───────────────────────────────────────────────────────
        topbar = QWidget()
        topbar.setFixedHeight(54)
        topbar.setStyleSheet(
            f"background:{C['header']};border-bottom:1px solid {C['border2']};")
        tbl = QHBoxLayout(topbar)
        tbl.setContentsMargins(18, 0, 18, 0)
        tbl.setSpacing(14)

        logo = QLabel('DJ MIX PLAYER')
        logo.setStyleSheet(
            f"color:{C['accent_lt']};font-family:'Courier New',Courier,monospace;font-size:14px;font-weight:bold;letter-spacing:3px;")
        tbl.addWidget(logo)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color:{C['border2']};")
        tbl.addWidget(sep)

        self._now_playing = QLabel('—')
        self._now_playing.setStyleSheet(
            f"color:{C['text_dim']};font-size:11px;max-width:320px;")
        tbl.addWidget(self._now_playing)
        tbl.addStretch()

        # Search
        self._search = QLineEdit()
        self._search.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._search.setPlaceholderText('  🔍  Buscar música...')
        self._search.setFixedWidth(260)
        self._search.setStyleSheet(f"""
            QLineEdit{{
                background:{C['panel']};
                border:1px solid {C['border2']};
                border-radius:16px;
                color:{C['text']};
                padding:6px 14px;
                font-size:12px;
            }}
            QLineEdit:focus{{border:1px solid {C['accent_lt']};}}
        """)
        self._search.textChanged.connect(self._on_search)
        tbl.addWidget(self._search)

        # Output device
        out_lbl = QLabel('SAÍDA')
        out_lbl.setStyleSheet(
            f"color:{C['text_dim']};font-size:9px;letter-spacing:1px;")
        tbl.addWidget(out_lbl)

        self._dev_combo = QComboBox()
        devs = self._engine.get_devices()
        self._dev_combo.addItems(devs)
        self._dev_combo.setFixedWidth(200)
        self._dev_combo.setStyleSheet(f"""
            QComboBox{{
                background:{C['panel']};
                border:1px solid {C['border2']};
                border-radius:5px;
                color:{C['text']};
                padding:5px 10px;
            }}
            QComboBox::drop-down{{border:none;width:18px;}}
            QComboBox QAbstractItemView{{
                background:{C['panel2']};
                border:1px solid {C['border2']};
                color:{C['text']};
                selection-background-color:{C['sel']};
                outline:none;
            }}
        """)
        tbl.addWidget(self._dev_combo)
        root.addWidget(topbar)

        # ── content area: sidebar + stack ────────────────────────────────
        content = QWidget()
        cl = QHBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        # Left sidebar with numbered tab buttons
        sidebar = QWidget()
        sidebar.setFixedWidth(46)
        sidebar.setStyleSheet(
            f"background:{C['header']};border-right:1px solid {C['border2']};")
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(5, 10, 5, 10)
        sl.setSpacing(6)

        self._tab_btns: list[QPushButton] = []
        for i in range(5):
            b = QPushButton(str(i + 1))
            b.setFixedSize(36, 36)
            b.setCheckable(True)
            b.setChecked(i == 0)
            b.clicked.connect(lambda _, idx=i: self._switch_tab(idx))
            self._tab_btns.append(b)
            sl.addWidget(b)
        sl.addStretch()
        self._update_tab_btns(0)
        cl.addWidget(sidebar)

        # Stacked pages
        from PyQt6.QtWidgets import QStackedWidget
        self._stack = QStackedWidget()
        for i in range(5):
            page = TabPage(i)
            page.sig_play.connect(self._play)
            self._pages.append(page)
            self._stack.addWidget(page)
        cl.addWidget(self._stack, 1)

        root.addWidget(content, 1)

        # ── bottom bar ────────────────────────────────────────────────────
        bottom = QWidget()
        bottom.setFixedHeight(150)
        bottom.setStyleSheet(
            f"background:{C['header']};border-top:1px solid {C['border2']};")
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 10, 0)
        bl.setSpacing(0)

        self._transport = TransportBar()
        self._transport.setStyleSheet("background:transparent;")
        bl.addWidget(self._transport, 1)

        # VU separator
        vsep = QFrame()
        vsep.setFrameShape(QFrame.Shape.VLine)
        vsep.setStyleSheet(f"color:{C['border2']};margin:10px 0;")
        bl.addWidget(vsep)

        # VU container — analógico + digital lado a lado
        vu_wrap = QWidget()
        vu_wrap.setFixedWidth(420)
        vul = QHBoxLayout(vu_wrap)
        vul.setContentsMargins(6, 4, 6, 4)
        vul.setSpacing(3)

        self._vu_l     = VUMeter('L')
        self._vu_r     = VUMeter('R')
        self._vubar_l  = DigitalVUBar()
        self._vubar_r  = DigitalVUBar()

        vul.addWidget(self._vu_l)
        vul.addWidget(self._vu_r)
        vul.addWidget(self._vubar_l)
        vul.addWidget(self._vubar_r)
        bl.addWidget(vu_wrap)

        root.addWidget(bottom)

    # ── signal wiring ─────────────────────────────────────────────────────
    def _wire(self):
        e = self._engine
        e.sig_pos  .connect(self._on_pos)
        e.sig_state.connect(self._transport.set_state)
        e.sig_dur  .connect(self._transport.set_duration)
        e.sig_vu   .connect(self._on_vu)
        e.sig_ended.connect(self._on_ended)

        t = self._transport
        t.sig_play  .connect(e.play)
        t.sig_pause .connect(e.pause)
        t.sig_stop  .connect(self._stop)
        t.sig_prev  .connect(self._prev)
        t.sig_next  .connect(self._next)
        t.sig_seek  .connect(e.seek)
        t.sig_volume.connect(e.set_volume)

    def _refresh_panel_styles(self):
        for pg in self._pages:
            for panel in pg.get_panels():
                panel.set_active(False)

    # ── tab navigation ────────────────────────────────────────────────────
    def _switch_tab(self, idx: int):
        self._stack.setCurrentIndex(idx)
        self._update_tab_btns(idx)

    def _update_tab_btns(self, active: int):
        for i, b in enumerate(self._tab_btns):
            if i == active:
                b.setStyleSheet(f"""
                    QPushButton{{
                        background:{C['accent']};
                        color:white;
                        border:none;
                        border-radius:8px;
                        font-size:15px;
                        font-weight:bold;
                    }}
                """)
            else:
                b.setStyleSheet(f"""
                    QPushButton{{
                        background:{C['panel2']};
                        color:{C['text_dim']};
                        border:1px solid {C['border2']};
                        border-radius:8px;
                        font-size:15px;
                        font-weight:bold;
                    }}
                    QPushButton:hover{{
                        background:{C['hover']};
                        color:{C['text']};
                        border:1px solid {C['accent']};
                    }}
                """)

    # ── slots ─────────────────────────────────────────────────────────────
    def _play(self, path: str):
        self._current = path

        # Encontra o painel e a linha da música
        self._cur_panel = None
        self._cur_row   = -1
        for pg in self._pages:
            for panel in pg.get_panels():
                if path in panel._songs:
                    self._cur_panel = panel
                    self._cur_row   = panel._songs.index(path)
                    break
            if self._cur_panel:
                break

        self._engine.stop()
        try:
            self._engine.load(path)
        except RuntimeError as e:
            ext = Path(path).suffix.upper()
            QMessageBox.warning(
                self, 'Formato não suportado',
                f'Não foi possível carregar o arquivo:\n{Path(path).name}\n\n'
                f'Formato {ext} não é suportado pelo backend de áudio.\n\n{e}'
            )
            return
        self._engine.play()
        name = display_name(path)
        self._transport.set_song(name)
        short = name[:50] + ('…' if len(name) > 50 else '')
        self._now_playing.setText(f'▶  {short}')
        for pg in self._pages:
            pg.set_playing(path)

    def _stop(self):
        self._engine.stop()
        self._current = None
        self._now_playing.setText('—')
        for pg in self._pages:
            pg.set_playing(None)

    def _on_pos(self, frac: float):
        self._transport.set_pos(frac, self._engine.pos_seconds())

    def _on_vu(self, l: float, r: float):
        self._vu_l.set_level(l)
        self._vu_r.set_level(r)
        self._vubar_l.set_level(l)
        self._vubar_r.set_level(r)

    def _prev(self):
        if self._cur_panel is not None and self._cur_row > 0:
            row = self._cur_row - 1
            self._play(self._cur_panel._songs[row])
            self._cur_panel._list.setCurrentRow(row)
            self._cur_panel._list.scrollToItem(self._cur_panel._list.item(row))

    def _next(self):
        if self._cur_panel is not None and self._cur_row >= 0:
            row = self._cur_row + 1
            if row < len(self._cur_panel._songs):
                self._play(self._cur_panel._songs[row])
                self._cur_panel._list.setCurrentRow(row)
                self._cur_panel._list.scrollToItem(self._cur_panel._list.item(row))

    def _on_ended(self):
        if self._cur_panel is not None and self._cur_row >= 0:
            row = self._cur_row + 1
            if row < len(self._cur_panel._songs):
                self._play(self._cur_panel._songs[row])
                self._cur_panel._list.setCurrentRow(row)
                self._cur_panel._list.scrollToItem(self._cur_panel._list.item(row))
                return
        self._current   = None
        self._cur_panel = None
        self._cur_row   = -1
        self._now_playing.setText('—')
        for pg in self._pages:
            pg.set_playing(None)

    def _on_search(self, q: str):
        for pg in self._pages:
            pg.filter(q)

    # ── persistence ───────────────────────────────────────────────────────
    def _save(self):
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = [pg.to_dict() for pg in self._pages]
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self):
        if not DATA_FILE.exists():
            return
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for i, pd in enumerate(data[:5]):
                self._pages[i].from_dict(pd)
        except Exception as e:
            print(f"load data: {e}")

    def closeEvent(self, ev):
        self._save()
        self._engine.stop()
        if HAS_PYGAME:
            pygame.quit()
        ev.accept()


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    if not HAS_PYGAME:
        print("AVISO: pygame não encontrado. Execute: pip install pygame")
    if not HAS_MUTAGEN:
        print("AVISO: mutagen não encontrado. Execute: pip install mutagen")

    app = QApplication(sys.argv)
    app.setApplicationName('DJ Mix Player')

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

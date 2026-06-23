#!/usr/bin/env python3
"""
DJ Mix Player
pip install PyQt6 pygame mutagen sounddevice
"""
import sys
import os
import json
import time
import random
import threading
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QListWidget, QListWidgetItem,
    QLineEdit, QComboBox, QFileDialog, QMessageBox, QMenu, QSlider,
    QTabWidget, QSizePolicy, QFrame, QScrollArea,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QMimeData, QUrl
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QRadialGradient, QFont, QDragEnterEvent, QDropEvent

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
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.ogg', '.aac', '.m4a', '.wma', '.opus'}
FORMATS_FILTER = "Áudio (*.mp3 *.wav *.flac *.ogg *.aac *.m4a *.wma *.opus);;Todos (*.*)"

C = {
    'bg':        '#0e1117',
    'panel':     '#141824',
    'panel2':    '#1a2030',
    'header':    '#111827',
    'border':    '#1e2a3d',
    'border2':   '#2a3a55',
    'accent':    '#2563eb',
    'accent2':   '#1d4ed8',
    'accent_lt': '#3b82f6',
    'text':      '#d1d5db',
    'text_dim':  '#6b7280',
    'playing':   '#22d3ee',
    'hover':     '#1e2d47',
    'sel':       '#1e3a5f',
    'vu_green':  '#22c55e',
    'vu_yellow': '#eab308',
    'vu_red':    '#ef4444',
}

PANEL_HEADERS = [
    '#1e3a5f', '#1a3550', '#162d44',
    '#1e3a5f', '#1a3550', '#162d44',
    '#1e3a5f', '#1a3550', '#162d44',
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
    if HAS_MUTAGEN:
        try:
            f = MutagenFile(path, easy=True)
            if f:
                title = f.get('title', [''])[0]
                artist = f.get('artist', [''])[0]
                if title and artist:
                    return f"{artist} — {title}"
                if title:
                    return title
        except Exception:
            pass
    return Path(path).stem


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
    def load(self, path: str):
        self._path = path
        if HAS_PYGAME:
            try:
                pygame.mixer.music.load(path)
                self._duration = 0
                if HAS_MUTAGEN:
                    f = MutagenFile(path)
                    if f and hasattr(f.info, 'length'):
                        self._duration = int(f.info.length)
                self.sig_dur.emit(self._duration)
            except Exception as e:
                print(f"load error: {e}")

    def play(self):
        if not self._path:
            return
        if HAS_PYGAME:
            if self._state == 'paused':
                pygame.mixer.music.unpause()
                self._t0 = time.time()
            else:
                pygame.mixer.music.play()
                self._t0 = time.time()
                self._offset = 0.0
            self._state = 'playing'
            self.sig_state.emit('playing')

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


# ── VU Meter ──────────────────────────────────────────────────────────────────
class VUMeter(QWidget):
    def __init__(self, ch='L', parent=None):
        super().__init__(parent)
        self.ch = ch
        self._lvl  = 0.0
        self._peak = 0.0
        self._hold = 0
        self.setMinimumWidth(32)
        self.setMaximumWidth(44)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

    def set_level(self, v: float):
        self._lvl = max(0.0, min(1.0, v))
        if self._lvl > self._peak:
            self._peak = self._lvl
            self._hold = 22
        else:
            if self._hold > 0:
                self._hold -= 1
            else:
                self._peak = max(0.0, self._peak - 0.015)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        SEGS = 28
        label_h = 18
        bar_h = h - label_h - 4
        seg_h = max(3, (bar_h - SEGS) // SEGS)
        gap   = 1

        p.fillRect(0, 0, w, h, QColor(C['bg']))

        filled   = int(self._lvl  * SEGS)
        peak_seg = int(self._peak * SEGS)

        for i in range(SEGS):
            y = 2 + bar_h - (i + 1) * (seg_h + gap)
            frac = i / SEGS
            if   frac > 0.86: color = QColor(C['vu_red'])
            elif frac > 0.65: color = QColor(C['vu_yellow'])
            else:              color = QColor(C['vu_green'])

            if i < filled:
                p.fillRect(5, y, w - 10, seg_h, color)
            else:
                dim = QColor(color); dim.setAlpha(30)
                p.fillRect(5, y, w - 10, seg_h, dim)

        # Peak hold bar
        if 0 < peak_seg < SEGS:
            py = 2 + bar_h - (peak_seg + 1) * (seg_h + gap)
            frac = peak_seg / SEGS
            if   frac > 0.86: pc = QColor(C['vu_red'])
            elif frac > 0.65: pc = QColor(C['vu_yellow'])
            else:              pc = QColor(C['vu_green'])
            pc.setAlpha(240)
            p.fillRect(5, py, w - 10, 2, pc)

        # Label
        p.setPen(QColor(C['text_dim']))
        f = QFont('Courier', 8, QFont.Weight.Bold)
        p.setFont(f)
        p.drawText(0, h - label_h, w, label_h,
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   self.ch)
        p.end()


# ── Playlist List ─────────────────────────────────────────────────────────────
class PlaylistList(QListWidget):
    pass


# ── Playlist Panel ────────────────────────────────────────────────────────────
class SongItem(QListWidgetItem):
    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self._name = display_name(path)
        self._dur  = get_duration(path)
        self.setText(f"  {self._name}")
        self.setToolTip(path)

    def matches(self, q: str) -> bool:
        return q in self._name.lower() or q in Path(self.path).name.lower()


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

        self._lbl = QLabel(self._name)
        self._lbl.setStyleSheet("color:white; font-weight:bold; font-size:10px; letter-spacing:1px;")
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
        self._list.setFont(QFont('Segoe UI', 11, QFont.Weight.Medium))
        self._apply_list_style(active=False)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._ctx)
        self._list.itemDoubleClicked.connect(lambda i: self.sig_play.emit(i.path))
        self._list.keyPressEvent = self._list_key_press
        layout.addWidget(self._list)

    def _apply_list_style(self, active: bool):
        border_color = C['accent_lt'] if active else C['border']
        bg_color     = '#17203a'      if active else C['panel']
        self._list.setStyleSheet(f"""
            QListWidget{{
                background:{bg_color};
                border:2px solid {border_color};
                border-top:none;
                border-radius:0 0 5px 5px;
                color:{C['text']};
                font-size:13px;
                outline:none;
            }}
            QListWidget::item{{
                height:28px;
                padding-left:6px;
                border-bottom:1px solid rgba(255,255,255,.05);
            }}
            QListWidget::item:selected{{background:{C['sel']};color:white;}}
            QListWidget::item:hover{{background:{C['hover']};}}
            QScrollBar:vertical{{
                background:{C['bg']};width:5px;border-radius:2px;
            }}
            QScrollBar::handle:vertical{{
                background:{C['border2']};border-radius:2px;min-height:20px;
            }}
            QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}
        """)

    def set_active(self, active: bool):
        self._apply_list_style(active)
        # Header border glow
        glow = f"2px solid {C['accent_lt']}" if active else f"2px solid {self._color}"
        self._hdr.setStyleSheet(
            f"background:{self._color};border-radius:5px 5px 0 0;"
            f"border:{glow};"
        )

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
            self._name = new_name.strip()
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
                it.setForeground(QColor(C['playing']))
                it.setFont(QFont('Segoe UI', 11, QFont.Weight.Bold))
                has_playing = True
            else:
                it.setForeground(QColor(C['text']))
                it.setFont(QFont('Segoe UI', 11, QFont.Weight.Medium))
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
    clicked = pyqtSignal()

    def __init__(self, icon: str, size: int = 60, accent: bool = False, parent=None):
        super().__init__(parent)
        self._icon    = icon
        self._sz      = size
        self._accent  = accent
        self._hovered = False
        self._pressed = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _):
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2
        r = min(w, h) // 2 - 4
        if self._pressed:
            r -= 2

        # Outer glow when hovered
        if self._hovered:
            gc = QColor(C['accent_lt'] if self._accent else '#3a4a6a')
            for i in range(7, 0, -1):
                gc.setAlpha(i * 8)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(gc)
                p.drawEllipse(cx - r - i, cy - r - i, (r + i) * 2, (r + i) * 2)

        # Circle fill
        p.setPen(Qt.PenStyle.NoPen)
        if self._accent:
            grad = QRadialGradient(cx, cy - r // 3, r * 1.2)
            grad.setColorAt(0.0, QColor('#5ba3ff'))
            grad.setColorAt(0.5, QColor(C['accent']))
            grad.setColorAt(1.0, QColor(C['accent2']))
        else:
            grad = QRadialGradient(cx, cy - r // 3, r * 1.2)
            grad.setColorAt(0.0, QColor('#2e3f5e'))
            grad.setColorAt(1.0, QColor('#151d2e'))
        p.setBrush(grad)
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        # Border ring
        pen_color = QColor(C['accent_lt'] if self._accent else C['border2'])
        if self._hovered:
            pen_color = QColor(C['accent_lt'])
        p.setPen(pen_color)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        # Icon text
        icon_font_size = max(10, r // 2 + 4)
        p.setPen(QColor('white'))
        f = QFont('Segoe UI Symbol', icon_font_size)
        f.setWeight(QFont.Weight.Bold)
        p.setFont(f)
        # Nudge ▶ slightly right for visual centering
        offset = 2 if self._icon == '▶' else 0
        p.drawText(offset, 0, w, h, Qt.AlignmentFlag.AlignCenter, self._icon)
        p.end()

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


# ── Transport Bar ─────────────────────────────────────────────────────────────
class TransportBar(QWidget):
    sig_play   = pyqtSignal()
    sig_pause  = pyqtSignal()
    sig_stop   = pyqtSignal()
    sig_seek   = pyqtSignal(float)
    sig_volume = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dur = 0
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 8, 20, 8)
        root.setSpacing(4)

        # ── Song title ────────────────────────────────────────────────────
        self._title = QLabel('Nenhuma música selecionada')
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setStyleSheet(
            f"color:{C['text_dim']};font-size:12px;font-weight:500;"
            "letter-spacing:0.3px;"
        )
        root.addWidget(self._title)

        # ── Seek bar ──────────────────────────────────────────────────────
        self._seek = SeekBar()
        self._seek.seeked.connect(self.sig_seek)
        root.addWidget(self._seek)

        # ── Main controls row ─────────────────────────────────────────────
        row = QHBoxLayout()
        row.setSpacing(0)
        row.setContentsMargins(0, 0, 0, 0)

        # Time elapsed
        time_col = QVBoxLayout()
        time_col.setSpacing(0)
        self._elapsed = QLabel('00:00')
        self._elapsed.setStyleSheet(
            f"color:{C['text']};font-family:'Courier New',Courier;"
            f"font-size:20px;font-weight:bold;letter-spacing:2px;"
        )
        self._total = QLabel('00:00')
        self._total.setStyleSheet(
            f"color:{C['text_dim']};font-family:'Courier New',Courier;"
            f"font-size:11px;letter-spacing:1px;"
        )
        time_col.addStretch()
        time_col.addWidget(self._elapsed)
        time_col.addWidget(self._total)
        time_col.addStretch()
        row.addLayout(time_col)

        row.addStretch()

        # Buttons — centered group
        btn_row = QHBoxLayout()
        btn_row.setSpacing(14)
        btn_row.setContentsMargins(0, 0, 0, 0)

        self._btn_stop  = TransportButton('⏹', size=48, accent=False)
        self._btn_play  = TransportButton('▶', size=60, accent=True)
        self._btn_pause = TransportButton('⏸', size=48, accent=False)
        for _b in (self._btn_stop, self._btn_play, self._btn_pause):
            _b.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._btn_stop .clicked.connect(self.sig_stop)
        self._btn_play .clicked.connect(self.sig_play)
        self._btn_pause.clicked.connect(self.sig_pause)

        btn_row.addWidget(self._btn_stop)
        btn_row.addWidget(self._btn_play)
        btn_row.addWidget(self._btn_pause)
        row.addLayout(btn_row)

        row.addStretch()

        # Volume column (right side)
        vol_col = QVBoxLayout()
        vol_col.setSpacing(4)
        vlbl = QLabel('VOLUME')
        vlbl.setStyleSheet(
            f"color:{C['text_dim']};font-size:9px;letter-spacing:2px;")
        vlbl.setAlignment(Qt.AlignmentFlag.AlignRight)

        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._vol.setRange(0, 100)
        self._vol.setValue(80)
        self._vol.setFixedWidth(130)
        self._vol.setStyleSheet(f"""
            QSlider::groove:horizontal{{
                height:5px;background:{C['border2']};border-radius:2px;
            }}
            QSlider::handle:horizontal{{
                background:white;width:14px;height:14px;
                border-radius:7px;margin:-5px 0;
                border:2px solid {C['accent']};
            }}
            QSlider::sub-page:horizontal{{
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {C['accent2']},stop:1 {C['accent_lt']});
                border-radius:2px;
            }}
        """)
        self._vol.valueChanged.connect(lambda v: self.sig_volume.emit(v / 100))
        vol_col.addStretch()
        vol_col.addWidget(vlbl)
        vol_col.addWidget(self._vol)
        vol_col.addStretch()
        row.addLayout(vol_col)

        root.addLayout(row)

    # ── public ────────────────────────────────────────────────────────────
    def set_song(self, name: str):
        metrics = self._title.fontMetrics()
        elided  = metrics.elidedText(name, Qt.TextElideMode.ElideMiddle, 340)
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

    # ── UI construction ───────────────────────────────────────────────────
    def _build(self):
        self.setStyleSheet(f"""
            QMainWindow,QWidget{{
                background:{C['bg']};
                color:{C['text']};
                font-family:'Segoe UI','Ubuntu',sans-serif;
                font-size:12px;
            }}
            QTabWidget::pane{{border:none;background:{C['bg']};}}
            QTabBar::tab{{
                background:{C['panel']};
                color:{C['text_dim']};
                padding:7px 22px;
                margin-right:2px;
                border-radius:4px 4px 0 0;
                font-weight:bold;font-size:13px;letter-spacing:2px;
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
            f"color:{C['accent_lt']};font-size:17px;font-weight:bold;letter-spacing:3px;")
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
        bottom.setFixedHeight(118)
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

        # VU container
        vu_wrap = QWidget()
        vu_wrap.setFixedWidth(104)
        vul = QHBoxLayout(vu_wrap)
        vul.setContentsMargins(10, 6, 6, 6)
        vul.setSpacing(6)

        self._vu_l = VUMeter('L')
        self._vu_r = VUMeter('R')
        vul.addWidget(self._vu_l)
        vul.addWidget(self._vu_r)
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
        t.sig_seek  .connect(e.seek)
        t.sig_volume.connect(e.set_volume)

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
        self._engine.load(path)
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

    def _on_ended(self):
        # Tenta tocar a próxima música no mesmo painel
        if self._cur_panel is not None and self._cur_row >= 0:
            next_row = self._cur_row + 1
            if next_row < len(self._cur_panel._songs):
                self._play(self._cur_panel._songs[next_row])
                # Rola a lista para mostrar a música tocando
                self._cur_panel._list.setCurrentRow(next_row)
                self._cur_panel._list.scrollToItem(
                    self._cur_panel._list.item(next_row))
                return

        # Fim da playlist — limpa estado
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

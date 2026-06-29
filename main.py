#!/usr/bin/env python3
"""
DJ Mix Player
pip install PyQt6 pygame mutagen sounddevice soundfile
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
    QTabWidget, QSizePolicy, QFrame, QScrollArea, QDialog,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QMimeData, QUrl, QPointF, QRectF, QSize
from PyQt6.QtGui import (QPainter, QColor, QLinearGradient, QRadialGradient, QFont,
                         QDragEnterEvent, QDropEvent, QPolygonF, QFontDatabase,
                         QPixmap, QIcon, QPen)

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

try:
    import soundfile as sf
    HAS_SF = True
except ImportError:
    HAS_SF = False

# ── Constants ─────────────────────────────────────────────────────────────────
AUDIO_EXTENSIONS = {'.mp3', '.mpa', '.wav', '.flac', '.ogg', '.aac', '.m4a', '.wma', '.opus', '.mp2', '.mp4'}
FORMATS_FILTER = "Áudio (*.mp3 *.mpa *.wav *.flac *.ogg *.aac *.m4a *.wma *.opus *.mp2 *.mp4);;Todos (*.*)"


def _flat_icon(kind: str, size: int = 16, color: str = '#ffffff') -> QIcon:
    """Gera ícone flat via QPainter. kind: 'lupa' | 'x'"""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)

    if kind == 'lupa':
        pen.setWidthF(size * 0.12)
        p.setPen(pen)
        r = int(size * 0.38)
        cx, cy = int(size * 0.38), int(size * 0.38)
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)
        hx = int(cx + r * 0.72)
        hy = int(cy + r * 0.72)
        p.drawLine(hx, hy, size - 1, size - 1)

    elif kind == 'x':
        pen.setWidthF(size * 0.14)
        p.setPen(pen)
        m = int(size * 0.18)
        p.drawLine(m, m, size - m, size - m)
        p.drawLine(size - m, m, m, size - m)

    p.end()
    return QIcon(px)

CUE_POINTS:  dict[str, list] = {}  # path → [frac_or_None] × 5
CUE_FADEIN:  dict[str, list] = {}  # path → [bool] × 5, True = fade-in ativo


def _cue_slots(path: str) -> list:
    if path not in CUE_POINTS:
        CUE_POINTS[path] = [None] * 5
    elif len(CUE_POINTS[path]) < 5:
        CUE_POINTS[path] = (CUE_POINTS[path] + [None] * 5)[:5]
    return CUE_POINTS[path]


def _cue_fadein(path: str) -> list:
    if path not in CUE_FADEIN:
        CUE_FADEIN[path] = [True] * 5
    elif len(CUE_FADEIN[path]) < 5:
        CUE_FADEIN[path] = (CUE_FADEIN[path] + [True] * 5)[:5]
    return CUE_FADEIN[path]

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

    @property
    def state(self): return self._state

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


# ── CUE Engine ────────────────────────────────────────────────────────────────
class CueEngine(QObject):
    sig_pos   = pyqtSignal(float)   # 0.0–1.0
    sig_state = pyqtSignal(str)     # playing / paused / stopped
    sig_ended = pyqtSignal()
    sig_dur   = pyqtSignal(int)     # seconds

    def __init__(self):
        super().__init__()
        self._path      = None
        self._data      = None   # numpy array loaded by soundfile
        self._samplerate = 44100
        self._channels  = 2
        self._state     = 'stopped'
        self._duration  = 0
        self._volume    = 0.8
        self._cursor    = 0      # sample cursor (frame index)
        self._lock      = threading.Lock()
        self._stream    = None
        self._device    = None   # None = default

        self._pos_timer = QTimer()
        self._pos_timer.setInterval(50)
        self._pos_timer.timeout.connect(self._emit_pos)
        self._pos_timer.start()

    # ── public API ─────────────────────────────────────────────────────────
    def get_devices(self) -> list:
        if HAS_SD:
            try:
                return [d['name'] for d in sd.query_devices()
                        if d['max_output_channels'] > 0]
            except Exception:
                pass
        return ['Dispositivo padrão']

    def set_device(self, name: str):
        self._device = name if name and name != 'Dispositivo padrão' else None

    def load(self, path: str) -> bool:
        self.stop()
        data, sr = None, 44100
        # primary: soundfile
        if HAS_SF:
            try:
                data, sr = sf.read(path, dtype='float32', always_2d=True)
            except Exception:
                pass
        # fallback: pygame sndarray (handles MP3 on Windows)
        if data is None and HAS_PYGAME:
            try:
                import numpy as np
                sound = pygame.mixer.Sound(path)
                arr   = pygame.sndarray.array(sound)
                arr   = arr.astype('float32') / 32768.0
                if arr.ndim == 1:
                    arr = arr.reshape(-1, 1)
                data = arr
                sr   = pygame.mixer.get_init()[0] or 44100
            except Exception as e2:
                print(f"CueEngine: não foi possível carregar audio: {e2}")
        if data is None:
            return False
        self._data       = data
        self._samplerate = int(sr)
        self._channels   = data.shape[1] if data.ndim > 1 else 1
        self._path       = path
        self._duration   = int(len(data) / self._samplerate)
        with self._lock:
            self._cursor = 0
        self.sig_dur.emit(self._duration)
        self.sig_state.emit('stopped')
        return True

    def play(self):
        if not HAS_SF:
            QMessageBox.warning(
                None, 'CUE indisponível',
                'soundfile não está instalado.\nExecute: pip install soundfile'
            )
            return
        if self._data is None:
            return
        if self._state == 'playing':
            return
        if self._state == 'paused':
            # resume — stream is still open; just change state flag
            self._state = 'playing'
            self.sig_state.emit('playing')
            return
        # stopped → start stream from cursor
        self._start_stream()
        self._state = 'playing'
        self.sig_state.emit('playing')

    def pause(self):
        if self._state == 'playing':
            self._state = 'paused'
            self.sig_state.emit('paused')

    def stop(self):
        self._state = 'stopped'
        self._close_stream()
        with self._lock:
            self._cursor = 0
        self.sig_state.emit('stopped')
        self.sig_pos.emit(0.0)

    def seek(self, frac: float):
        if self._data is None:
            return
        total = len(self._data)
        new_cursor = int(max(0.0, min(1.0, frac)) * total)
        was_playing = self._state == 'playing'
        if was_playing:
            self._close_stream()
        with self._lock:
            self._cursor = new_cursor
        if was_playing:
            self._start_stream()
            self._state = 'playing'
            self.sig_state.emit('playing')

    def seek_instant(self, frac: float):
        """Move cursor for real-time scrubbing. Never restarts an open stream."""
        if self._data is None:
            return
        with self._lock:
            self._cursor = int(max(0.0, min(1.0, frac)) * len(self._data))
        if self._state != 'playing':
            self._state = 'playing'
            self.sig_state.emit('playing')
            if self._stream is None:          # only open stream if truly closed
                self._start_stream()

    def set_volume(self, v: float):
        self._volume = max(0.0, min(1.0, v))

    # ── internal ───────────────────────────────────────────────────────────
    def _start_stream(self):
        self._close_stream()
        if not HAS_SD or self._data is None:
            return
        try:
            kwargs = dict(
                samplerate=self._samplerate,
                channels=self._channels,
                dtype='float32',
                callback=self._callback,
                finished_callback=self._on_finished,
            )
            if self._device is not None:
                kwargs['device'] = self._device
            self._stream = sd.OutputStream(**kwargs)
            self._stream.start()
        except Exception as e:
            print(f"CueEngine stream error: {e}")
            self._stream = None

    def _close_stream(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _callback(self, outdata, frames, time_info, status):
        if self._state != 'playing' or self._data is None:
            outdata[:] = 0
            return
        with self._lock:
            start = self._cursor
            end   = start + frames
            chunk = self._data[start:end]
            self._cursor = min(end, len(self._data))

        n = len(chunk)
        if n < frames:
            outdata[:n]  = chunk * self._volume
            outdata[n:]  = 0
        else:
            outdata[:] = chunk * self._volume

    def _on_finished(self):
        # Called from sounddevice thread when stream finishes
        if self._state == 'playing':
            self._state = 'stopped'
            with self._lock:
                self._cursor = 0
            self.sig_state.emit('stopped')
            self.sig_ended.emit()

    def _emit_pos(self):
        if self._data is None or len(self._data) == 0:
            return
        with self._lock:
            cursor = self._cursor
        frac = cursor / len(self._data)
        self.sig_pos.emit(frac)

    @property
    def state(self): return self._state
    @property
    def duration(self): return self._duration


class WaveformWidget(QWidget):
    seeked   = pyqtSignal(float)   # on mouse release
    scrubbed = pyqtSignal(float)   # on mouse move during drag

    def __init__(self, parent=None):
        super().__init__(parent)
        self._peaks        = None
        self._error_msg    = ''
        self._pos          = 0.0
        self._cues: list   = [None] * 5
        self._drag         = False
        self._zoom         = 1.0
        self._view_start   = 0.0
        self._last_scrub_t = 0.0   # for throttling scrubbed signal
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_data(self, peaks):
        self._peaks = peaks
        self._error_msg = ''
        self.update()

    def set_error(self, msg: str):
        self._peaks = []
        self._error_msg = msg
        self.update()

    def set_pos(self, frac: float):
        self._pos = max(0.0, min(1.0, frac))
        self._auto_scroll()
        self.update()

    def set_cues(self, slots: list):
        """slots: list of 5 items, each None or float frac."""
        self._cues = (list(slots) + [None] * 5)[:5]
        self.update()

    def set_zoom(self, factor: float):
        self._zoom = max(1.0, min(32.0, factor))
        self._auto_scroll()
        self.update()

    def _auto_scroll(self):
        """Keep playhead in the middle third of the view when zoomed."""
        if self._zoom <= 1.0:
            self._view_start = 0.0
            return
        win = 1.0 / self._zoom
        lo  = self._pos - win * 0.5
        self._view_start = max(0.0, min(1.0 - win, lo))

    def _view_end(self) -> float:
        return min(1.0, self._view_start + 1.0 / self._zoom)

    def _frac_to_x(self, frac: float, w: int) -> int:
        win = self._view_end() - self._view_start
        if win <= 0:
            return 0
        return int((frac - self._view_start) / win * w)

    def _x_to_frac(self, x: int, w: int) -> float:
        win = self._view_end() - self._view_start
        return max(0.0, min(1.0, self._view_start + (x / w) * win))

    def paintEvent(self, _):
        from PyQt6.QtGui import QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        p.fillRect(0, 0, w, h, QColor('#0a0e14'))

        if self._peaks is None or len(self._peaks) == 0:
            p.setPen(QColor(C['text_dim']))
            p.setFont(QFont('Roboto', 10))
            msg = self._error_msg if self._error_msg else 'Carregando waveform...'
            p.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, msg)
            p.end()
            return

        peaks = self._peaks
        n     = len(peaks)
        cy    = h / 2.0
        v_start = self._view_start
        v_end   = self._view_end()
        win     = v_end - v_start

        playhead_x = self._frac_to_x(self._pos, w)

        accent = QColor(C['accent'])
        for x in range(w):
            frac_x = v_start + (x / w) * win
            idx = int(frac_x * n)
            idx = max(0, min(n - 1, idx))
            peak_val = float(peaks[idx])
            bar_h = max(1, int(peak_val * (h - 6)))
            col = QColor(accent)
            col.setAlpha(200 if x < playhead_x else 60)
            p.fillRect(x, int(cy - bar_h / 2), 1, bar_h, col)

        # CUE markers
        CUE_COLORS = ['#ffcc00', '#ff6600', '#00dd88', '#cc44ff', '#ff4466']
        for i, frac in enumerate(self._cues):
            if frac is None:
                continue
            if not (v_start <= frac <= v_end):
                continue
            cx_cue = self._frac_to_x(frac, w)
            cue_col = QColor(CUE_COLORS[i % len(CUE_COLORS)])
            p.setPen(QPen(cue_col, 2))
            p.drawLine(cx_cue, 0, cx_cue, h)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(cue_col)
            tri = QPolygonF([
                QPointF(cx_cue - 6, 0),
                QPointF(cx_cue + 6, 0),
                QPointF(cx_cue,     10),
            ])
            p.drawPolygon(tri)
            p.setPen(QColor('#111111'))
            p.setFont(QFont('Roboto', 6, QFont.Weight.Bold))
            p.drawText(cx_cue - 6, 0, 12, 10, Qt.AlignmentFlag.AlignCenter, str(i + 1))

        # Playhead
        p.setPen(QPen(QColor('white'), 2))
        p.drawLine(playhead_x, 0, playhead_x, h)

        # Zoom indicator bar at bottom (only when zoomed)
        if self._zoom > 1.0:
            bar_y = h - 4
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(80, 80, 80, 120))
            p.drawRect(0, bar_y, w, 4)
            bx = int(self._view_start * w)
            bw = max(4, int(w / self._zoom))
            p.setBrush(QColor(C['accent_lt']))
            p.drawRect(bx, bar_y, bw, 4)

        p.end()

    def mousePressEvent(self, e):
        self._drag = True
        frac = self._x_to_frac(int(e.position().x()), self.width())
        self._pos = frac
        self._last_scrub_t = 0.0
        self.update()
        self._emit_scrubbed(frac)

    def mouseMoveEvent(self, e):
        if self._drag:
            frac = self._x_to_frac(int(e.position().x()), self.width())
            self._pos = frac
            self.update()          # visual always fluid
            self._emit_scrubbed(frac)

    def mouseReleaseEvent(self, e):
        if self._drag:
            frac = self._x_to_frac(int(e.position().x()), self.width())
            self._drag = False
            self.seeked.emit(frac)

    def _emit_scrubbed(self, frac: float):
        now = time.monotonic()
        if now - self._last_scrub_t >= 0.030:   # max ~33 Hz
            self._last_scrub_t = now
            self.scrubbed.emit(frac)

    def wheelEvent(self, e):
        delta = e.angleDelta().y()
        factor = self._zoom * (1.15 if delta > 0 else 1/1.15)
        self.set_zoom(factor)


# ── CUE Window ────────────────────────────────────────────────────────────────
class CueWindow(QDialog):
    sig_waveform_ready  = pyqtSignal(object)
    sig_waveform_error  = pyqtSignal(str)
    sig_cue_changed     = pyqtSignal(str)

    def __init__(self, cue_engine: 'CueEngine', parent=None):
        super().__init__(parent)
        self._engine      = cue_engine
        self._path        = None
        self._cur_pos     = 0.0
        self._scrub_timer = None   # created lazily, but reused after first scrub
        self.setWindowTitle('Editor CUE — Pré-escuta')
        self.setMinimumSize(860, 540)
        self.resize(960, 600)
        self.setModal(False)
        self._build()
        self._connect()
        # Intercept keyboard before any child widget steals it
        QApplication.instance().installEventFilter(self)

    def _build(self):
        self.setStyleSheet(f"""
            QDialog{{
                background:{C['bg']};
                color:{C['text']};
                font-family:'Roboto','DejaVu Sans','Arial',sans-serif;
            }}
            QLabel{{color:{C['text']};font-size:12px;font-weight:bold;}}
            QPushButton{{
                background:{C['panel2']};
                color:{C['text']};
                border:1px solid {C['border2']};
                border-radius:5px;
                padding:6px 16px;
                font-size:12px;
                font-weight:bold;
            }}
            QPushButton:hover{{background:{C['hover']};border:1px solid {C['accent']};}}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        # Header row: title + track name + close
        hdr_row = QHBoxLayout()
        hdr_lbl = QLabel('🎧  EDITOR CUE — PRÉ-ESCUTA')
        hdr_lbl.setStyleSheet(
            f"color:{C['accent_lt']};font-size:14px;font-weight:bold;letter-spacing:2px;")
        self._track_lbl = QLabel('—')
        self._track_lbl.setStyleSheet(
            f"color:{C['text_dim']};font-size:12px;")
        self._track_lbl.setWordWrap(False)
        hdr_row.addWidget(hdr_lbl)
        hdr_row.addSpacing(16)
        hdr_row.addWidget(self._track_lbl, 1)
        btn_close = QPushButton('✕  FECHAR')
        btn_close.setFixedHeight(30)
        btn_close.clicked.connect(self._on_close)
        hdr_row.addWidget(btn_close)
        root.addLayout(hdr_row)

        # Waveform
        self._waveform = WaveformWidget()
        self._waveform.setMinimumHeight(130)
        root.addWidget(self._waveform)

        # Zoom controls + time
        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(6)
        zoom_lbl = QLabel('ZOOM:')
        zoom_lbl.setStyleSheet(f"color:{C['text_dim']};font-size:11px;letter-spacing:1px;")
        zoom_row.addWidget(zoom_lbl)

        _zoom_btn_style = f"""
            QPushButton{{background:{C['panel']};color:{C['text_dim']};
                border:1px solid {C['border']};border-radius:4px;
                font-size:11px;font-weight:bold;padding:2px 10px;}}
            QPushButton:hover{{color:{C['text']};border-color:{C['border2']};}}
        """
        for label, factor in [('1×', 1.0), ('2×', 2.0), ('4×', 4.0), ('8×', 8.0), ('16×', 16.0)]:
            b = QPushButton(label)
            b.setFixedHeight(24)
            b.setStyleSheet(_zoom_btn_style)
            b.clicked.connect(lambda _, f=factor: self._waveform.set_zoom(f))
            zoom_row.addWidget(b)

        zoom_row.addSpacing(12)
        self._time_lbl = QLabel('00:00')
        self._time_lbl.setStyleSheet(
            f"color:{C['text']};font-size:18px;font-weight:bold;font-family:'Courier New',monospace;")
        zoom_row.addWidget(self._time_lbl)
        zoom_row.addStretch()

        self._dur_lbl = QLabel('/ 00:00')
        self._dur_lbl.setStyleSheet(
            f"color:{C['text_dim']};font-size:13px;font-family:'Courier New',monospace;")
        zoom_row.addWidget(self._dur_lbl)
        root.addLayout(zoom_row)

        # Transport row
        trans_row = QHBoxLayout()
        trans_row.setSpacing(8)
        self._btn_play = QPushButton('▶  PLAY')
        self._btn_play.setFixedHeight(36)
        self._btn_play.setStyleSheet(
            f"QPushButton{{background:{C['accent']};color:white;border:none;"
            f"border-radius:5px;padding:0 22px;font-weight:bold;font-size:13px;}}"
            f"QPushButton:hover{{background:{C['accent_lt']};}}"
        )
        self._btn_stop = QPushButton('■  STOP')
        self._btn_stop.setFixedHeight(36)

        # Volume
        vol_lbl = QLabel('VOL')
        vol_lbl.setStyleSheet(f"color:{C['text_dim']};font-size:11px;letter-spacing:1px;")
        self._vol = VolumeSlider()
        self._vol.set_value(0.8)

        trans_row.addWidget(self._btn_play)
        trans_row.addWidget(self._btn_stop)
        trans_row.addSpacing(16)
        trans_row.addWidget(vol_lbl)
        trans_row.addWidget(self._vol)
        trans_row.addStretch()
        root.addLayout(trans_row)

        # ── CUE Slots (5 buttons) ─────────────────────────────────────────
        cue_section_lbl = QLabel('PONTOS CUE  —  clique num slot vazio para marcar a posição atual · clique num slot marcado para ir até ele')
        cue_section_lbl.setStyleSheet(
            f"color:{C['text_dim']};font-size:10px;letter-spacing:1px;margin-top:6px;")
        root.addWidget(cue_section_lbl)

        cue_row = QHBoxLayout()
        cue_row.setSpacing(8)
        self._cue_slot_btns:  list[QPushButton] = []
        self._cue_fade_btns:  list[QPushButton] = []
        CUE_SLOT_COLORS = ['#b8860b', '#b85000', '#007744', '#6600aa', '#aa0033']
        for i in range(5):
            col = CUE_SLOT_COLORS[i]

            col_layout = QVBoxLayout()
            col_layout.setSpacing(3)

            btn = QPushButton(f'CUE {i+1}\n  — : —  ')
            btn.setFixedHeight(54)
            btn.setMinimumWidth(130)
            btn.setCheckable(False)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setStyleSheet(f"""
                QPushButton{{
                    background:{C['panel']};
                    color:{C['text_dim']};
                    border:2px solid {C['border']};
                    border-radius:6px;
                    font-size:11px;
                    font-weight:bold;
                    text-align:center;
                    padding:4px;
                }}
                QPushButton:hover{{
                    background:{C['hover']};
                    border-color:{col};
                    color:{C['text']};
                }}
            """)
            btn.clicked.connect(lambda _, idx=i: self._slot_clicked(idx))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, idx=i: self._slot_ctx(idx))
            self._cue_slot_btns.append(btn)
            col_layout.addWidget(btn)

            fade_btn = QPushButton('FADE IN  ✓')
            fade_btn.setFixedHeight(20)
            fade_btn.setCheckable(True)
            fade_btn.setChecked(True)
            fade_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self._apply_fade_btn_style(fade_btn, True)
            fade_btn.toggled.connect(lambda checked, idx=i: self._fade_toggled(idx, checked))
            self._cue_fade_btns.append(fade_btn)
            col_layout.addWidget(fade_btn)

            cue_row.addLayout(col_layout)
        root.addLayout(cue_row)

        # bottom row: info + limpar todos
        bot_row = QHBoxLayout()
        info_lbl = QLabel('Espaço = play/pause  ·  ← / → = navegar  ·  Shift+← / → = 5s  ·  Clique direito no slot → limpar  ·  Scroll = zoom')
        info_lbl.setStyleSheet(f"color:{C['text_dim']};font-size:10px;")
        bot_row.addWidget(info_lbl, 1)
        self._btn_clear_all = QPushButton('  LIMPAR TODOS OS CUEs')
        _ico_x_gray = _flat_icon('x', 14, '#888888')
        _ico_x_red  = _flat_icon('x', 14, '#ff6666')
        self._btn_clear_all.setIcon(_ico_x_gray)
        self._btn_clear_all.setIconSize(QSize(14, 14))
        self._btn_clear_all.setFixedHeight(28)
        self._btn_clear_all.setStyleSheet(
            f"QPushButton{{background:transparent;color:{C['text_dim']};"
            f"border:1px solid {C['border']};border-radius:4px;"
            f"font-size:10px;font-weight:bold;padding:0 10px;}}"
            f"QPushButton:hover{{color:#ff6666;border-color:#ff6666;}}"
        )
        _b = self._btn_clear_all
        def _btn_enter(e, b=_b, i=_ico_x_red):
            b.setIcon(i)
            QPushButton.enterEvent(b, e)
        def _btn_leave(e, b=_b, i=_ico_x_gray):
            b.setIcon(i)
            QPushButton.leaveEvent(b, e)
        _b.enterEvent = _btn_enter
        _b.leaveEvent = _btn_leave
        self._btn_clear_all.clicked.connect(self._clear_all_cues)
        bot_row.addWidget(self._btn_clear_all)
        root.addLayout(bot_row)

    def _connect(self):
        e = self._engine
        e.sig_pos  .connect(self._on_pos)
        e.sig_state.connect(self._on_state)
        e.sig_dur  .connect(self._on_dur)

        self._waveform.seeked.connect(self._on_seeked)
        self._waveform.scrubbed.connect(self._on_scrubbed)
        self._vol.changed.connect(e.set_volume)

        self._btn_play.clicked.connect(self._toggle)
        self._btn_stop.clicked.connect(e.stop)

        self.sig_waveform_ready.connect(self._waveform.set_data)
        self.sig_waveform_error.connect(self._waveform.set_error)

    # ── public ────────────────────────────────────────────────────────────
    def load(self, path: str):
        self._path = path
        self._track_lbl.setText(display_name(path))
        self._engine.load(path)        # loads but does NOT play
        self._waveform.set_data(None)
        self._waveform.set_zoom(1.0)
        slots = _cue_slots(path)
        self._waveform.set_cues(slots)
        self._refresh_slot_buttons()
        fi = _cue_fadein(path)
        for idx, fb in enumerate(self._cue_fade_btns):
            fb.blockSignals(True)
            fb.setChecked(fi[idx])
            self._apply_fade_btn_style(fb, fi[idx])
            fb.blockSignals(False)
        def _load_wf():
            import numpy as np
            data = None
            if HAS_SF:
                try:
                    raw, _ = sf.read(path, dtype='float32', always_2d=True)
                    data = raw
                except Exception:
                    pass
            if data is None and HAS_PYGAME:
                try:
                    sound = pygame.mixer.Sound(path)
                    arr   = pygame.sndarray.array(sound).astype('float32') / 32768.0
                    if arr.ndim == 1:
                        arr = arr.reshape(-1, 1)
                    data = arr
                except Exception as e2:
                    print(f"waveform pygame fallback: {e2}")
            if data is None:
                self.sig_waveform_error.emit('Waveform não disponível para este formato')
                return
            try:
                mono     = data.mean(axis=1) if data.ndim > 1 else data
                n_chunks = 1800
                total    = len(mono)
                chunk_sz = max(1, total // n_chunks)
                peaks = []
                for i in range(n_chunks):
                    s  = i * chunk_sz
                    e2 = min(s + chunk_sz, total)
                    peaks.append(float(np.abs(mono[s:e2]).max()) if s < total else 0.0)
                mx = max(peaks) if peaks else 1.0
                if mx > 0:
                    peaks = [v / mx for v in peaks]
                self.sig_waveform_ready.emit(peaks)
            except Exception as ex:
                self.sig_waveform_error.emit(f'Erro ao gerar waveform: {ex}')
        threading.Thread(target=_load_wf, daemon=True).start()

    def clear(self):
        self._engine.stop()
        self._path = None
        self._track_lbl.setText('—')
        self._waveform.set_pos(0.0)
        self._waveform.set_data(None)
        self._waveform.set_cues([None]*5)
        self._time_lbl.setText('00:00')
        self._dur_lbl.setText('/ 00:00')
        self._btn_play.setText('▶  PLAY')
        for btn in self._cue_slot_btns:
            btn.setText(f"CUE {self._cue_slot_btns.index(btn)+1}\n  — : —  ")

    # ── slots / handlers ──────────────────────────────────────────────────
    def _toggle(self):
        if self._engine.state == 'playing':
            self._engine.pause()
        else:
            self._engine.play()

    def _on_seeked(self, frac: float):
        self._engine.seek(frac)

    def _on_scrubbed(self, frac: float):
        """Real-time scrub: move cursor only, stream stays open for scratch audio."""
        self._engine.seek_instant(frac)
        if self._scrub_timer is None:
            self._scrub_timer = QTimer(self)
            self._scrub_timer.setSingleShot(True)
            self._scrub_timer.timeout.connect(self._scrub_stop)
        self._scrub_timer.start(350)   # pause 350ms after last movement

    def _scrub_stop(self):
        self._engine.pause()
        # keep timer object alive for reuse — just don't null it

    def _slot_clicked(self, idx: int):
        if not self._path:
            return
        slots = _cue_slots(self._path)
        if slots[idx] is None:
            # Mark current position
            slots[idx] = self._cur_pos
            CUE_POINTS[self._path] = slots
            self._waveform.set_cues(slots)
            self._refresh_slot_buttons()
            self.sig_cue_changed.emit(self._path)
        else:
            # Seek to this CUE
            self._engine.seek(slots[idx])
            if self._engine.state != 'playing':
                self._engine.play()

    def _slot_ctx(self, idx: int):
        if not self._path:
            return
        slots = _cue_slots(self._path)
        if slots[idx] is None:
            return
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu{{background:{C['panel2']};border:1px solid {C['border2']};
                   color:{C['text']};padding:4px;}}
            QMenu::item{{padding:5px 18px;border-radius:3px;}}
            QMenu::item:selected{{background:{C['sel']};}}
        """)
        a_clear = menu.addAction(f'✕  Limpar CUE {idx+1}')
        action = menu.exec(self._cue_slot_btns[idx].mapToGlobal(
            self._cue_slot_btns[idx].rect().center()))
        if action == a_clear:
            slots[idx] = None
            CUE_POINTS[self._path] = slots
            self._waveform.set_cues(slots)
            self._refresh_slot_buttons()
            self.sig_cue_changed.emit(self._path)

    def _refresh_slot_buttons(self):
        CUE_SLOT_COLORS = ['#b8860b', '#b85000', '#007744', '#6600aa', '#aa0033']
        CUE_SLOT_COLORS_LT = ['#ffcc00', '#ff6600', '#00dd88', '#cc44ff', '#ff4466']
        if not self._path:
            for i, btn in enumerate(self._cue_slot_btns):
                col = CUE_SLOT_COLORS[i]
                btn.setText(f"CUE {i+1}\n  — : —  ")
                btn.setStyleSheet(f"""
                    QPushButton{{background:{C['panel']};color:{C['text_dim']};
                        border:2px solid {C['border']};border-radius:6px;
                        font-size:11px;font-weight:bold;text-align:center;padding:4px;}}
                    QPushButton:hover{{background:{C['hover']};border-color:{col};color:{C['text']};}}
                """)
            return
        slots = _cue_slots(self._path)
        dur = self._engine.duration
        for i, btn in enumerate(self._cue_slot_btns):
            frac = slots[i]
            col  = CUE_SLOT_COLORS[i]
            clt  = CUE_SLOT_COLORS_LT[i]
            if frac is None:
                btn.setText(f"CUE {i+1}\n  — : —  ")
                btn.setStyleSheet(f"""
                    QPushButton{{background:{C['panel']};color:{C['text_dim']};
                        border:2px solid {C['border']};border-radius:6px;
                        font-size:11px;font-weight:bold;text-align:center;padding:4px;}}
                    QPushButton:hover{{background:{C['hover']};border-color:{col};color:{C['text']};}}
                """)
            else:
                secs = int(frac * dur) if dur else 0
                m, s = secs // 60, secs % 60
                btn.setText(f"CUE {i+1}\n  {m:02d}:{s:02d}  ")
                btn.setStyleSheet(f"""
                    QPushButton{{background:{col};color:white;
                        border:2px solid {clt};border-radius:6px;
                        font-size:11px;font-weight:bold;text-align:center;padding:4px;}}
                    QPushButton:hover{{background:{clt};border-color:white;}}
                """)

    def _on_pos(self, frac: float):
        self._cur_pos = frac
        self._waveform.set_pos(frac)
        dur = self._engine.duration
        secs = int(frac * dur)
        m, s = secs // 60, secs % 60
        self._time_lbl.setText(f"{m:02d}:{s:02d}")

    def _on_state(self, state: str):
        self._btn_play.setText('⏸  PAUSE' if state == 'playing' else '▶  PLAY')

    def _on_dur(self, secs: int):
        m, s = secs // 60, secs % 60
        self._dur_lbl.setText(f"/ {m:02d}:{s:02d}")
        self._refresh_slot_buttons()

    def _apply_fade_btn_style(self, btn: QPushButton, checked: bool):
        if checked:
            btn.setText('FADE IN  ✓')
            btn.setStyleSheet(f"""
                QPushButton{{
                    background:#1a3a1a;color:#44dd88;
                    border:1px solid #2a6a2a;border-radius:3px;
                    font-size:9px;font-weight:bold;letter-spacing:1px;
                }}
                QPushButton:hover{{background:#224422;}}
            """)
        else:
            btn.setText('FADE IN  ✗')
            btn.setStyleSheet(f"""
                QPushButton{{
                    background:{C['panel']};color:{C['text_dim']};
                    border:1px solid {C['border']};border-radius:3px;
                    font-size:9px;font-weight:bold;letter-spacing:1px;
                }}
                QPushButton:hover{{background:{C['hover']};color:{C['text']};}}
            """)

    def _fade_toggled(self, idx: int, checked: bool):
        if self._path:
            fi = _cue_fadein(self._path)
            fi[idx] = checked
            CUE_FADEIN[self._path] = fi
        self._apply_fade_btn_style(self._cue_fade_btns[idx], checked)

    def _clear_all_cues(self):
        if not self._path:
            return
        CUE_POINTS[self._path] = [None] * 5
        self._waveform.set_cues([None] * 5)
        self._refresh_slot_buttons()
        self.sig_cue_changed.emit(self._path)

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if self.isVisible() and event.type() == QEvent.Type.KeyPress:
            key  = event.key()
            mods = event.modifiers()
            ctrl  = bool(mods & Qt.KeyboardModifier.ControlModifier)
            shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
            if key == Qt.Key.Key_Space:
                self._toggle()
                return True
            dur = self._engine.duration
            if dur > 0 and key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
                # Ctrl = 5s, Shift = 1s, plain = 0.1s
                if ctrl:
                    step = 5.0
                elif shift:
                    step = 1.0
                else:
                    step = 0.1
                delta = step / dur
                if key == Qt.Key.Key_Left:
                    new_frac = max(0.0, self._cur_pos - delta)
                else:
                    new_frac = min(1.0, self._cur_pos + delta)
                self._engine.seek(new_frac)
                return True
        return False

    def _on_close(self):
        self._engine.stop()
        self.hide()

    def closeEvent(self, ev):
        ev.ignore()
        self._engine.stop()
        self.hide()

    def __del__(self):
        try:
            QApplication.instance().removeEventFilter(self)
        except Exception:
            pass


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

        margin = 4
        cx = w / 2.0
        # r limitado para que topo da face (cy - r - ARC_W) não saia do widget
        # ARC_W ≈ r/5 → r + r/5 = 6r/5 ≤ cy → r ≤ 5*cy/6
        r_tmp  = int(min((cx - 2) * 5.0 / 6.0, h - margin - 4))
        ARC_W  = max(6, r_tmp // 5)
        cy     = float(h - ARC_W - margin)
        r      = int(min((cx - 2) * 5.0 / 6.0, cy * 5.0 / 6.0 - 1))
        ARC_W  = max(6, r // 5)
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
                p.setFont(QFont('Roboto', max(5, r // 12), QFont.Weight.Bold))
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
        p.setFont(QFont('Roboto', 10, QFont.Weight.Bold))
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


# ── Digital VU Bar Horizontal ─────────────────────────────────────────────────
class HDigitalVUBar(QWidget):
    def __init__(self, label='L', parent=None):
        super().__init__(parent)
        self._lvl  = 0.0
        self._peak = 0.0
        self._hold = 0
        self._label = label
        self.setFixedHeight(10)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

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

        LBL_W = 14
        bar_w = w - LBL_W - 4
        SEG, GAP = 3, 1
        STEP  = SEG + GAP
        total = max(1, bar_w // STEP)
        lit   = int(self._lvl * total)

        p.setPen(QColor('#555555'))
        p.setFont(QFont('Roboto', 7, QFont.Weight.Bold))
        p.drawText(0, 0, LBL_W, h, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter, self._label)

        x0 = LBL_W + 2
        for i in range(total):
            pct = i / total
            color = (C['vu_red'] if pct >= 0.85 else
                     C['vu_yellow'] if pct >= 0.65 else C['vu_green'])
            x = x0 + i * STEP
            if i < lit:
                p.fillRect(x, 1, SEG, h - 2, QColor(color))
            else:
                dim = QColor(color); dim.setAlpha(30)
                p.fillRect(x, 1, SEG, h - 2, dim)

        if self._peak > 0.02:
            pk_i = min(int(self._peak * total), total - 1)
            pk_x = x0 + pk_i * STEP
            pk_c = (C['vu_red'] if self._peak >= 0.85 else
                    C['vu_yellow'] if self._peak >= 0.65 else C['vu_green'])
            p.fillRect(pk_x, 1, SEG, h - 2, QColor(pk_c))
        p.end()


# ── Delegate: garante cor verde na música tocando em qualquer estado ──────────
from PyQt6.QtWidgets import QStyledItemDelegate, QStyle
from PyQt6.QtGui import QColor

class SongDelegate(QStyledItemDelegate):
    PLAYING_ROLE = Qt.ItemDataRole.UserRole + 2

    def paint(self, painter, option, index):
        playing = index.data(self.PLAYING_ROLE)
        path = index.data(Qt.ItemDataRole.UserRole)  # SongItem._PATH_ROLE
        has_cues = bool(path and path in CUE_POINTS and any(v is not None for v in CUE_POINTS[path]))
        cue_count = sum(1 for v in CUE_POINTS.get(path, []) if v is not None)

        if playing:
            painter.save()
            # Fundo verde-escuro sempre, independente de seleção/foco
            painter.fillRect(option.rect, QColor('#0a2a14'))
            # Texto verde
            painter.setPen(QColor('#00dd55'))
            font = option.font
            font.setBold(True)
            painter.setFont(font)
            right_pad = 50 if has_cues else 4
            painter.drawText(
                option.rect.adjusted(8, 0, -right_pad, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                index.data(Qt.ItemDataRole.DisplayRole) or ''
            )
            painter.restore()
        else:
            # Draw CUE badge padding before default paint so text doesn't overlap
            if has_cues:
                painter.save()
                # Draw normal background first
                super().paint(painter, option, index)
                painter.restore()
                # Overdraw text with reduced right margin handled via default paint
                # (badge drawn below)
            else:
                super().paint(painter, option, index)

        # Draw CUE badge on right side for any item with CUE points
        if has_cues:
            painter.save()
            badge_text = f"◉ {cue_count}"
            badge_font = QFont('Roboto', 9, QFont.Weight.Bold)
            painter.setFont(badge_font)
            painter.setPen(QColor('#00ccff'))
            painter.drawText(
                option.rect.adjusted(0, 0, -6, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                badge_text
            )
            painter.restore()


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
    sig_play  = pyqtSignal(str)
    sig_cue   = pyqtSignal(str)
    sig_focus = pyqtSignal(str)

    def __init__(self, name: str, color: str, parent=None):
        super().__init__(parent)
        self._name   = name
        self._color  = color
        self._songs: list[str] = []
        self._repeat = 0   # 0=off  1=repeat one  2=repeat all
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
        self._lbl.setStyleSheet("color:white; font-weight:bold; font-size:15px; font-family:'Roboto','DejaVu Sans','Arial',sans-serif; letter-spacing:1px;")
        self._lbl.mouseDoubleClickEvent = lambda _: self._rename()
        self._lbl.setCursor(Qt.CursorShape.IBeamCursor)
        self._lbl.setToolTip('Duplo clique para renomear')
        hl.addWidget(self._lbl)
        hl.addStretch()

        self._btn_repeat = QPushButton('↻')
        self._btn_repeat.setFixedSize(26, 20)
        self._btn_repeat.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_repeat.setToolTip('Repetir: OFF')
        self._btn_repeat.clicked.connect(self._cycle_repeat)
        self._apply_repeat_style()
        hl.addWidget(self._btn_repeat)

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
                             border-radius:3px;font-size:13px;}
                QPushButton:hover{background:rgba(255,255,255,.28);}
            """)
            b.clicked.connect(fn)
            hl.addWidget(b)

        layout.addWidget(hdr)

        # ── sub-header: count + filter ────────────────────────────────────
        subhdr = QWidget()
        subhdr.setFixedHeight(30)
        subhdr.setStyleSheet(f"background:{self._darker(self._color)};")
        shl = QHBoxLayout(subhdr)
        shl.setContentsMargins(6, 0, 4, 0)
        shl.setSpacing(4)

        self._count = QLabel("0 músicas")
        self._count.setStyleSheet(
            "color:rgba(255,255,255,.5);font-size:11px;")
        shl.addWidget(self._count)
        shl.addStretch()

        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText('FILTRAR...')
        self._filter_edit.setFixedSize(260, 20)
        self._filter_edit.setStyleSheet("""
            QLineEdit{
                background:rgba(0,0,0,.3);
                border:none;
                border-radius:3px;
                color:rgba(255,255,255,.8);
                font-size:10px;
                padding:0 4px 0 2px;
            }
            QLineEdit:focus{
                background:rgba(0,0,0,.55);
            }
        """)
        from PyQt6.QtGui import QPen, QPixmap, QIcon
        _px = QPixmap(14, 14)
        _px.fill(Qt.GlobalColor.transparent)
        _pi = QPainter(_px)
        _pi.setRenderHint(QPainter.RenderHint.Antialiasing)
        _pi.setPen(QPen(QColor('white'), 1.5))
        _pi.setBrush(Qt.BrushStyle.NoBrush)
        _pi.drawEllipse(1, 1, 8, 8)
        _pi.drawLine(8, 8, 13, 13)
        _pi.end()
        self._filter_edit.addAction(
            QIcon(_px), QLineEdit.ActionPosition.LeadingPosition)
        self._filter_edit.textChanged.connect(self.filter)
        shl.addWidget(self._filter_edit)

        self._btn_clear = QPushButton('✕')
        self._btn_clear.setFixedSize(18, 18)
        self._btn_clear.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_clear.setStyleSheet("""
            QPushButton{
                background:rgba(255,255,255,.08);
                color:rgba(255,255,255,.4);
                border:none;
                border-radius:3px;
                font-size:9px;
                font-weight:bold;
            }
            QPushButton:hover{
                background:rgba(255,255,255,.2);
                color:rgba(255,255,255,.9);
            }
        """)
        self._btn_clear.clicked.connect(self._filter_edit.clear)
        shl.addWidget(self._btn_clear)

        layout.addWidget(subhdr)

        # ── song list ─────────────────────────────────────────────────────
        self._list = PlaylistList()
        self._list.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._list.setFont(QFont('Roboto', 15, QFont.Weight.Bold))
        self._list.setItemDelegate(SongDelegate())
        self._apply_list_style(active=False)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._ctx)
        self._list.itemDoubleClicked.connect(lambda i: self.sig_play.emit(i.path))
        self._list.currentItemChanged.connect(
            lambda cur, _: self.sig_focus.emit(cur.path) if cur else None)
        self._list.itemClicked.connect(
            lambda item: self.sig_focus.emit(item.path) if item else None)
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
                font-family:'Roboto','DejaVu Sans','Arial',sans-serif;
                font-size:15px;
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

    def _apply_repeat_style(self):
        _REPEAT_STYLES = [
            # off — transparente/dim
            ("↻",  'Repetir: OFF',
             "QPushButton{background:rgba(255,255,255,.10);color:rgba(255,255,255,.40);"
             "border:none;border-radius:3px;font-size:13px;font-weight:bold;}"
             "QPushButton:hover{background:rgba(255,255,255,.22);color:white;}"),
            # repeat 1 — azul accent
            ("↻1", 'Repetir: 1 música',
             "QPushButton{background:#1464b4;color:white;"
             "border:none;border-radius:3px;font-size:11px;font-weight:bold;}"
             "QPushButton:hover{background:#1878d4;}"),
            # repeat all — verde
            ("↻∞", 'Repetir: tudo',
             "QPushButton{background:#1a7a3a;color:white;"
             "border:none;border-radius:3px;font-size:11px;font-weight:bold;}"
             "QPushButton:hover{background:#22aa44;}"),
        ]
        text, tip, style = _REPEAT_STYLES[self._repeat]
        self._btn_repeat.setText(text)
        self._btn_repeat.setToolTip(tip)
        self._btn_repeat.setStyleSheet(style)

    def _cycle_repeat(self):
        self._repeat = (self._repeat + 1) % 3
        self._apply_repeat_style()

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
            a_cue    = menu.addAction('🎧  CUE')
            menu.addSeparator()
            a_rename = menu.addAction('✎  Renomear playlist')
            menu.addSeparator()
            a_remove = menu.addAction('✕  Remover da lista')
            action = menu.exec(self._list.mapToGlobal(pos))
            if action == a_play:
                self.sig_play.emit(item.path)
            elif action == a_cue:
                self.sig_cue.emit(item.path)
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

    def to_dict(self) -> dict:
        return {'name': self._name, 'songs': self._songs, 'repeat': self._repeat}

    def from_dict(self, d: dict):
        self._name = d.get('name', self._name)
        self._lbl.setText(self._name)
        self._repeat = int(d.get('repeat', 0)) % 3
        self._apply_repeat_style()
        for p in d.get('songs', []):
            if os.path.exists(p):
                self.add_song(p)

    def _upd_count(self):
        n = self._list.count()
        self._count.setText(f"  {n} música{'s' if n != 1 else ''}")

    @staticmethod
    def _darker(hex_col: str) -> str:
        return QColor(hex_col).darker(140).name()


# ── Tab Page (grid configurável) ──────────────────────────────────────────────
class TabPage(QWidget):
    sig_play  = pyqtSignal(str)
    sig_cue   = pyqtSignal(str)
    sig_focus = pyqtSignal(str)

    def __init__(self, idx: int, cols: int = 3, rows: int = 3, parent=None):
        super().__init__(parent)
        self._panels: list[PlaylistPanel] = []
        self._idx  = idx
        self._cols = cols
        self._rows = rows
        self._build()

    def _build(self):
        g = QGridLayout(self)
        g.setSpacing(7)
        g.setContentsMargins(8, 8, 8, 8)
        for i in range(self._rows * self._cols):
            r, c = divmod(i, self._cols)
            panel = PlaylistPanel(
                f"PLAYLIST {i + 1 + self._idx * self._rows * self._cols}",
                PANEL_HEADERS[i % len(PANEL_HEADERS)]
            )
            panel.sig_play.connect(self.sig_play)
            panel.sig_cue.connect(self.sig_cue)
            panel.sig_focus.connect(self.sig_focus)
            self._panels.append(panel)
            g.addWidget(panel, r, c)
        for c in range(self._cols):  g.setColumnStretch(c, 1)
        for r in range(self._rows):  g.setRowStretch(r, 1)

        lists = [p._list for p in self._panels]
        for i in range(len(lists) - 1):
            QWidget.setTabOrder(lists[i], lists[i + 1])
        QWidget.setTabOrder(lists[-1], lists[0])

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
        root.setContentsMargins(16, 2, 16, 2)
        root.setSpacing(1)

        # ── Linha 1: tempo (esq) | nome da música (centro) ──────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(0)
        top_row.setContentsMargins(0, 0, 0, 0)

        self._title = QLabel('Nenhuma música selecionada')
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setFixedHeight(22)
        self._title.setStyleSheet(
            f"color:{C['text_dim']};font-size:13px;font-weight:500;"
            "letter-spacing:0.5px;"
        )
        top_row.addWidget(self._title, 1)
        root.addLayout(top_row)

        # ── Linha 2: seek bar largura total ──────────────────────────────
        self._seek = SeekBar()
        self._seek.seeked.connect(self.sig_seek)
        root.addWidget(self._seek)

        # ── Linha 3: tempo | botões | volume ─────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.setContentsMargins(12, 2, 0, 0)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Tempo à esquerda dos botões
        self._elapsed = QLabel('00:00')
        self._elapsed.setStyleSheet(
            f"color:{C['text']};font-family:'Courier New',Courier;"
            f"font-size:20px;font-weight:bold;letter-spacing:3px;"
        )
        self._total = QLabel('00:00')
        self._total.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._total.setStyleSheet(
            f"color:{C['text_dim']};font-family:'Courier New',Courier;"
            f"font-size:13px;letter-spacing:1px;"
        )
        time_col = QVBoxLayout()
        time_col.setSpacing(0)
        time_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        time_col.addWidget(self._elapsed)
        time_col.addWidget(self._total)
        btn_row.addLayout(time_col)

        self._btn_prev      = TransportButton('prev', size=32, accent=False)
        self._btn_stop      = TransportButton('stop', size=36, accent=False)
        self._btn_playpause = TransportButton('play', size=52, accent=True)
        self._btn_next      = TransportButton('next', size=32, accent=False)

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
            f"color:{C['text_dim']};font-size:11px;letter-spacing:2px;font-weight:bold;")
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


# ── Settings Dialog ───────────────────────────────────────────────────────────
class MusicSearchDialog(QDialog):
    sig_play = pyqtSignal(str)
    sig_add  = pyqtSignal(str, int)   # path, índice global do painel

    MAX_RESULTS = 300

    def __init__(self, music_folder: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Buscar Música')
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.resize(640, 520)
        self._playlist_names: list[str] = []
        self.setStyleSheet(f"background:{C['bg']};color:{C['text']};")
        self._folder     = music_folder
        self._all_files: list[str] = []
        self._scan_result: list | None = None   # preenchido pela thread, lido pelo timer

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        title = QLabel('BUSCAR MÚSICA')
        title.setStyleSheet(
            f"color:{C['accent_lt']};font-size:14px;font-weight:bold;letter-spacing:2px;")
        root.addWidget(title)

        self._folder_lbl = QLabel(f'Pasta: {music_folder or "(não configurada em ⚙ CONFIG.)"}')
        self._folder_lbl.setStyleSheet(f"color:{C['text_dim']};font-size:10px;")
        root.addWidget(self._folder_lbl)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText('Digite o nome da música...')
        self._search_edit.setFixedHeight(36)
        self._search_edit.setStyleSheet(f"""
            QLineEdit{{
                background:{C['panel']};border:1px solid {C['border2']};
                border-radius:5px;color:{C['text']};padding:6px 10px;font-size:13px;
            }}
            QLineEdit:focus{{border-color:{C['accent_lt']};}}
        """)
        self._search_edit.returnPressed.connect(self._do_search)

        _btn_search_style = (
            f"QPushButton{{background:{C['accent']};color:white;border:none;"
            f"border-radius:5px;font-size:13px;font-weight:bold;padding:0 18px;}}"
            f"QPushButton:hover{{background:{C['accent_lt']};}}"
            f"QPushButton:disabled{{background:{C['panel2']};color:{C['text_dim']};}}"
        )
        self._btn_go = QPushButton('  BUSCAR')
        self._btn_go.setIcon(_flat_icon('lupa', 16, '#ffffff'))
        self._btn_go.setIconSize(QSize(16, 16))
        self._btn_go.setFixedHeight(36)
        self._btn_go.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_go.setEnabled(False)
        self._btn_go.setStyleSheet(_btn_search_style)
        self._btn_go.clicked.connect(self._do_search)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search_row.addWidget(self._search_edit, 1)
        search_row.addWidget(self._btn_go)
        root.addLayout(search_row)

        self._status_lbl = QLabel('Aguardando...')
        self._status_lbl.setStyleSheet(f"color:{C['text_dim']};font-size:10px;")
        root.addWidget(self._status_lbl)

        self._list = QListWidget()
        self._list.setStyleSheet(f"""
            QListWidget{{
                background:{C['panel']};border:1px solid {C['border']};
                border-radius:5px;color:{C['text']};font-size:14px;outline:none;
            }}
            QListWidget::item{{padding:8px 12px;border-bottom:1px solid {C['border']};}}
            QListWidget::item:selected{{background:{C['sel']};color:white;}}
            QListWidget::item:hover{{background:{C['hover']};}}
        """)
        self._list.itemDoubleClicked.connect(self._on_item_activated)
        self._list.itemActivated.connect(self._on_item_activated)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._ctx_menu)
        root.addWidget(self._list, 1)

        hint = QLabel('Duplo clique ou Enter para tocar  ·  Botão direito para adicionar à playlist')
        hint.setStyleSheet(f"color:{C['text_dim']};font-size:10px;")
        root.addWidget(hint)

        # Timer polling: evita emitir sinal cross-thread (mais seguro no Windows/PyQt6)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(200)
        self._poll_timer.timeout.connect(self._check_scan)

        if music_folder and Path(music_folder).is_dir():
            self._start_scan(music_folder)
        else:
            self._status_lbl.setText(
                'Pasta não configurada. Defina em ⚙ CONFIG. e reabra a busca.')

    def set_folder(self, folder: str):
        self._folder = folder
        self._folder_lbl.setText(f'Pasta: {folder or "(não configurada)"}')
        self._all_files = []
        self._scan_result = None
        self._list.clear()
        if folder and Path(folder).is_dir():
            self._start_scan(folder)
        else:
            self._status_lbl.setText('Pasta inválida.')

    def _start_scan(self, folder: str):
        self._scan_result = None
        self._status_lbl.setText('Buscando arquivos...')
        self._list.clear()

        def _scan():
            results = []
            try:
                for p in Path(folder).rglob('*'):
                    try:
                        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS:
                            results.append(str(p))
                            if len(results) >= 20000:
                                break
                    except Exception:
                        continue
            except Exception:
                pass
            try:
                results.sort(key=lambda x: Path(x).name.lower())
            except Exception:
                pass
            self._scan_result = results   # escrita atômica, lida pelo timer

        threading.Thread(target=_scan, daemon=True).start()
        self._poll_timer.start()

    def _check_scan(self):
        if self._scan_result is None:
            return
        self._poll_timer.stop()
        paths = self._scan_result
        self._scan_result = None
        self._all_files = paths
        n = len(paths)
        if n == 0:
            self._status_lbl.setText('Nenhum arquivo de áudio encontrado nessa pasta.')
            self._btn_go.setEnabled(False)
        else:
            self._status_lbl.setText(
                f'{n} arquivo{"s" if n != 1 else ""} encontrado{"s" if n != 1 else ""}'
                ' — digite e clique BUSCAR')
            self._btn_go.setEnabled(True)
            self._search_edit.setFocus()

    def _do_search(self):
        term = self._search_edit.text().lower().strip()
        if not self._all_files:
            return
        self._list.setUpdatesEnabled(False)
        self._list.clear()
        shown = 0
        for path in self._all_files:
            if not term or term in Path(path).name.lower():
                item = QListWidgetItem(display_name(path))
                item.setData(Qt.ItemDataRole.UserRole, path)
                item.setToolTip(path)
                self._list.addItem(item)
                shown += 1
                if shown >= self.MAX_RESULTS:
                    break
        self._list.setUpdatesEnabled(True)

        total = len(self._all_files)
        if shown >= self.MAX_RESULTS and shown < total:
            self._status_lbl.setText(f'Mostrando {shown} de {total} — refine a busca')
        else:
            self._status_lbl.setText(
                f'{shown} resultado{"s" if shown != 1 else ""} de {total} arquivos')

        if shown > 0:
            self._list.setCurrentRow(0)
            self._list.setFocus()

    def set_playlists(self, names: list[str]):
        self._playlist_names = names

    def _ctx_menu(self, pos):
        item = self._list.itemAt(pos)
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu{{background:{C['panel2']};border:1px solid {C['border2']};
                   color:{C['text']};padding:4px;}}
            QMenu::item{{padding:6px 18px;border-radius:3px;font-size:13px;}}
            QMenu::item:selected{{background:{C['sel']};}}
            QMenu::separator{{height:1px;background:{C['border2']};margin:3px 0;}}
        """)
        act_play = menu.addAction('▶  Tocar agora')
        menu.addSeparator()
        add_actions = []
        for i, name in enumerate(self._playlist_names):
            add_actions.append((menu.addAction(f'+ Adicionar a  {name}'), i))
        action = menu.exec(self._list.viewport().mapToGlobal(pos))
        if action == act_play:
            self.sig_play.emit(path)
        else:
            for act, idx in add_actions:
                if action == act:
                    self.sig_add.emit(path, idx)
                    break

    def _on_item_activated(self, item):
        if item:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path:
                self.sig_play.emit(path)

    def _play_selected(self):
        self._on_item_activated(self._list.currentItem())


class SettingsDialog(QDialog):
    def __init__(self, devices: list, main_device: str, cue_device: str,
                 music_folder: str = '', parent=None):
        super().__init__(parent)
        self.setWindowTitle('Configurações')
        self.setModal(True)
        self.setFixedSize(520, 300)
        self.setStyleSheet(f"background:{C['bg']};color:{C['text']};")
        _combo_style = f"""
            QComboBox{{
                background:{C['panel']};
                border:1px solid {C['border2']};
                border-radius:5px;
                color:{C['text']};
                padding:5px 10px;
                font-size:13px;
            }}
            QComboBox::drop-down{{border:none;width:18px;}}
            QComboBox QAbstractItemView{{
                background:{C['panel2']};
                border:1px solid {C['border2']};
                color:{C['text']};
                selection-background-color:{C['sel']};
                outline:none;
            }}
        """
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(18)

        title = QLabel('⚙  CONFIGURAÇÕES')
        title.setStyleSheet(
            f"color:{C['accent_lt']};font-size:14px;font-weight:bold;letter-spacing:2px;")
        root.addWidget(title)

        form = QGridLayout()
        form.setSpacing(12)
        form.setColumnMinimumWidth(0, 110)

        lbl_main = QLabel('SAÍDA')
        lbl_main.setStyleSheet(f"color:{C['text_dim']};font-size:12px;letter-spacing:1px;")
        self._main_combo = QComboBox()
        self._main_combo.addItems(devices)
        self._main_combo.setStyleSheet(_combo_style)
        if main_device:
            idx = self._main_combo.findText(main_device)
            if idx >= 0:
                self._main_combo.setCurrentIndex(idx)
        form.addWidget(lbl_main, 0, 0)
        form.addWidget(self._main_combo, 0, 1)

        lbl_cue = QLabel('PRÉ ESCUTA')
        lbl_cue.setStyleSheet(f"color:{C['text_dim']};font-size:12px;letter-spacing:1px;")
        self._cue_combo = QComboBox()
        self._cue_combo.addItems(devices)
        self._cue_combo.setStyleSheet(_combo_style)
        if cue_device:
            idx = self._cue_combo.findText(cue_device)
            if idx >= 0:
                self._cue_combo.setCurrentIndex(idx)
        form.addWidget(lbl_cue, 1, 0)
        form.addWidget(self._cue_combo, 1, 1)

        lbl_folder = QLabel('PASTA MÚSICAS')
        lbl_folder.setStyleSheet(f"color:{C['text_dim']};font-size:12px;letter-spacing:1px;")
        folder_row = QHBoxLayout()
        folder_row.setSpacing(6)
        self._folder_edit = QLineEdit()
        self._folder_edit.setReadOnly(True)
        self._folder_edit.setText(music_folder)
        self._folder_edit.setPlaceholderText('(nenhuma pasta selecionada)')
        self._folder_edit.setStyleSheet(f"""
            QLineEdit{{
                background:{C['panel']};border:1px solid {C['border2']};
                border-radius:5px;color:{C['text']};padding:5px 10px;font-size:12px;
            }}
        """)
        btn_browse = QPushButton('...')
        btn_browse.setFixedSize(34, 34)
        btn_browse.setStyleSheet(f"""
            QPushButton{{background:{C['panel2']};color:{C['text']};
                border:1px solid {C['border2']};border-radius:5px;font-weight:bold;}}
            QPushButton:hover{{background:{C['hover']};border-color:{C['accent_lt']};}}
        """)
        btn_browse.clicked.connect(self._browse_folder)
        folder_row.addWidget(self._folder_edit)
        folder_row.addWidget(btn_browse)
        form.addWidget(lbl_folder, 2, 0)
        form.addLayout(folder_row, 2, 1)

        root.addLayout(form)
        root.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton('Cancelar')
        btn_cancel.setFixedHeight(34)
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton('OK')
        btn_ok.setFixedHeight(34)
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addSpacing(8)
        btn_row.addWidget(btn_ok)
        root.addLayout(btn_row)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Selecionar pasta de músicas',
                                                  self._folder_edit.text() or str(Path.home()))
        if folder:
            self._folder_edit.setText(folder)

    def main_device(self) -> str:
        return self._main_combo.currentText()

    def cue_device(self) -> str:
        return self._cue_combo.currentText()

    def music_folder(self) -> str:
        return self._folder_edit.text()


# ── Main Window ───────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._engine        = AudioEngine()
        self._cue_engine    = CueEngine()
        self._current: str | None = None
        self._pages:   list[TabPage] = []
        self._cur_panel     = None   # PlaylistPanel com a música atual
        self._cur_row       = -1     # índice da música atual no painel
        self._main_device:  str = ''
        self._cue_device:   str = ''
        self._music_folder: str = ''
        self._search_dlg: MusicSearchDialog | None = None
        self._focused: str | None = None   # song with keyboard/mouse focus
        self._build()
        self._cue_window = CueWindow(self._cue_engine, self)
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
                font-family:'Roboto','DejaVu Sans','Arial',sans-serif;
                font-size:11px;
                font-weight:bold;
            }}
            QTabWidget::pane{{border:none;background:{C['bg']};}}
            QTabBar::tab{{
                background:{C['panel']};
                color:{C['text_dim']};
                padding:5px 18px;
                margin-right:2px;
                border-radius:3px 3px 0 0;
                font-weight:bold;font-size:13px;letter-spacing:1px;
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
                font-family:'Roboto','DejaVu Sans','Arial',sans-serif;
                font-size:17px;
                font-weight:bold;
            }}
            QDialog QLabel, QMessageBox QLabel, QInputDialog QLabel{{
                color:{C['text']};
                font-size:17px;
                font-weight:bold;
            }}
            QDialog QLineEdit, QInputDialog QLineEdit{{
                background:{C['panel']};
                color:{C['text']};
                border:1px solid {C['border2']};
                border-radius:4px;
                padding:6px 10px;
                font-size:17px;
                font-weight:bold;
            }}
            QDialog QPushButton, QMessageBox QPushButton, QInputDialog QPushButton{{
                background:{C['accent']};
                color:white;
                border:none;
                border-radius:5px;
                padding:8px 24px;
                font-size:16px;
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
                font-size: 13px;
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

        logo = QLabel('DJ MIX')
        logo.setStyleSheet(
            f"color:{C['accent_lt']};font-family:'Courier New',Courier,monospace;font-size:16px;font-weight:bold;letter-spacing:3px;")
        tbl.addWidget(logo)

        tbl.addSpacing(16)

        _cue_btn_style = f"""
            QPushButton{{
                background:{C['panel']};
                color:{C['text_dim']};
                border:1px solid {C['border']};
                border-radius:5px;
                font-size:11px;
                font-weight:bold;
                letter-spacing:1px;
                padding:0 10px;
                min-width:48px;
            }}
            QPushButton:hover{{
                background:{C['hover']};
                color:{C['text']};
                border-color:{C['border2']};
            }}
            QPushButton:checked{{
                background:{C['accent2']};
                color:white;
                border-color:{C['accent_lt']};
            }}
        """
        self._cue_btns: list[QPushButton] = []
        for i in range(1, 6):
            b = QPushButton(f'CUE {i}')
            b.setFixedHeight(34)
            b.setCheckable(True)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setStyleSheet(_cue_btn_style)
            self._cue_btns.append(b)
            tbl.addWidget(b)

        tbl.addSpacing(12)

        # Buscar música button
        self._btn_search = QPushButton('  BUSCAR MÚSICA')
        self._btn_search.setIcon(_flat_icon('lupa', 15, '#cccccc'))
        self._btn_search.setIconSize(QSize(15, 15))
        self._btn_search.setFixedHeight(34)
        self._btn_search.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_search.setEnabled(False)   # habilitado só quando pasta configurada
        self._btn_search.setToolTip('Configure a pasta de músicas em ⚙ CONFIG. para habilitar')
        self._btn_search.setStyleSheet(f"""
            QPushButton{{
                background:{C['panel2']};color:{C['text']};
                border:1px solid {C['border2']};border-radius:5px;
                font-size:11px;font-weight:bold;letter-spacing:1px;padding:0 14px;
            }}
            QPushButton:hover{{
                background:{C['hover']};color:{C['accent_lt']};
                border-color:{C['accent_lt']};
            }}
            QPushButton:disabled{{
                background:{C['panel']};color:{C['text_dim']};
                border-color:{C['border']};
            }}
        """)
        self._btn_search.clicked.connect(self._open_search)
        tbl.addWidget(self._btn_search)

        tbl.addStretch()

        # Settings gear button
        self._btn_settings = QPushButton('⚙  CONFIG.')
        self._btn_settings.setFixedHeight(36)
        self._btn_settings.setToolTip('Configurações')
        self._btn_settings.setStyleSheet(f"""
            QPushButton{{
                background:transparent;
                color:{C['text_dim']};
                border:1px solid {C['border']};
                border-radius:5px;
                font-size:12px;
                font-weight:bold;
                letter-spacing:1px;
                padding:0 12px;
            }}
            QPushButton:hover{{
                color:{C['accent_lt']};
                border-color:{C['border2']};
            }}
        """)
        self._btn_settings.clicked.connect(self._open_settings)
        tbl.addWidget(self._btn_settings)

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
        for i in range(8):
            b = QPushButton(str(i + 1))
            b.setFixedSize(36, 36)
            b.setCheckable(True)
            b.setChecked(i == 0)
            b.clicked.connect(lambda _, idx=i: self._switch_tab(idx))
            self._tab_btns.append(b)
            sl.addWidget(b)

        sl.addStretch()

        # Botões de seleção de layout
        lyt_lbl = QLabel('LAYOUT')
        lyt_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lyt_lbl.setStyleSheet(f"color:{C['text_dim']};font-size:8px;font-weight:bold;letter-spacing:1px;")
        sl.addWidget(lyt_lbl)

        self._layout_btns: list[QPushButton] = []
        for label, cols, rows in [('3×3', 3, 3), ('4×3', 4, 3)]:
            b = QPushButton(label)
            b.setFixedSize(36, 24)
            b.setCheckable(True)
            b.setChecked(cols == 3)
            b.clicked.connect(lambda _, c=cols, r=rows: self._set_grid_layout(c, r))
            b.setStyleSheet(f"""
                QPushButton{{background:{C['panel']};color:{C['text_dim']};
                    border:1px solid {C['border2']};border-radius:4px;
                    font-size:10px;font-weight:bold;}}
                QPushButton:checked{{background:{C['accent']};color:white;border:none;}}
                QPushButton:hover:!checked{{background:{C['hover']};color:{C['text']};}}
            """)
            self._layout_btns.append(b)
            sl.addWidget(b)

        self._update_tab_btns(0)
        cl.addWidget(sidebar)

        # Stacked pages
        from PyQt6.QtWidgets import QStackedWidget
        self._grid_cols = 3
        self._grid_rows = 3
        self._stack = QStackedWidget()
        for i in range(8):
            page = TabPage(i, self._grid_cols, self._grid_rows)
            page.sig_play.connect(self._play)
            page.sig_cue.connect(self._on_cue)
            page.sig_focus.connect(self._on_focus)
            self._pages.append(page)
            self._stack.addWidget(page)
        cl.addWidget(self._stack, 1)

        root.addWidget(content, 1)

        # ── bottom bar ────────────────────────────────────────────────────
        bottom = QWidget()
        bottom.setFixedHeight(136)
        bottom.setStyleSheet(
            f"background:{C['header']};")
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

        # VU container — barras horizontais no topo + analógicos embaixo
        vu_wrap = QWidget()
        vu_wrap.setFixedWidth(420)
        vu_root = QVBoxLayout(vu_wrap)
        vu_root.setContentsMargins(6, 0, 6, 4)
        vu_root.setSpacing(2)

        self._hvu_l = HDigitalVUBar('L')
        self._hvu_r = HDigitalVUBar('R')
        vu_root.addWidget(self._hvu_l)
        vu_root.addWidget(self._hvu_r)

        self._vu_l = VUMeter('L')
        self._vu_r = VUMeter('R')
        analog_row = QHBoxLayout()
        analog_row.setSpacing(3)
        analog_row.setContentsMargins(0, 10, 0, 0)
        analog_row.addWidget(self._vu_l)
        analog_row.addWidget(self._vu_r)
        vu_root.addLayout(analog_row)

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

        self._cue_window.sig_cue_changed.connect(self._on_cue_changed)

        for i, b in enumerate(self._cue_btns):
            b.clicked.connect(lambda _, idx=i: self._on_cue_btn(idx))

    def _on_cue_changed(self, path: str):
        # Repaint all playlist lists so the CUE badge appears/updates
        for pg in self._pages:
            for panel in pg.get_panels():
                panel._list.update()
        self._refresh_cue_buttons()

    def _on_focus(self, path: str):
        self._focused = path
        self._refresh_cue_buttons()

    def _refresh_cue_buttons(self):
        CUE_SLOT_COLORS = ['#7a5800', '#7a3000', '#005533', '#440077', '#770022']
        CUE_SLOT_COLORS_LT = ['#ffcc00', '#ff6600', '#00dd88', '#cc44ff', '#ff4466']
        path = self._focused or self._current
        slots = _cue_slots(path) if path else [None] * 5
        for i, btn in enumerate(self._cue_btns):
            frac = slots[i]
            col  = CUE_SLOT_COLORS[i]
            clt  = CUE_SLOT_COLORS_LT[i]
            if frac is not None:
                btn.setChecked(True)
                btn.setStyleSheet(f"""
                    QPushButton{{
                        background:{col};
                        color:{clt};
                        border:1px solid {clt};
                        border-radius:5px;
                        font-size:11px;
                        font-weight:bold;
                        letter-spacing:1px;
                        padding:0 10px;
                        min-width:48px;
                    }}
                    QPushButton:hover{{background:{clt};color:white;}}
                """)
            else:
                btn.setChecked(False)
                btn.setStyleSheet(f"""
                    QPushButton{{
                        background:{C['panel']};
                        color:{C['text_dim']};
                        border:1px solid {C['border']};
                        border-radius:5px;
                        font-size:11px;
                        font-weight:bold;
                        letter-spacing:1px;
                        padding:0 10px;
                        min-width:48px;
                    }}
                    QPushButton:hover{{
                        background:{C['hover']};
                        color:{C['text']};
                        border-color:{C['border2']};
                    }}
                """)

    def _on_cue_btn(self, idx: int):
        # Use focused song if available, fallback to current playing
        path = self._focused or self._current
        if not path:
            return
        slots = _cue_slots(path)
        frac = slots[idx]
        if frac is None:
            return
        # Load song if it's not the one currently in the engine
        if path != self._current:
            self._engine.stop()
            try:
                self._engine.load(path)
            except RuntimeError:
                return
            self._current = path
            name = display_name(path)
            self._transport.set_song(name)
            for pg in self._pages:
                pg.set_playing(path)
        use_fade = _cue_fadein(path)[idx]
        was_playing = self._engine.state == 'playing'
        if use_fade:
            target_vol = self._engine._volume
            self._engine.set_volume(0.0)
        self._engine.seek(frac)
        if not was_playing:
            self._engine.play()
        if use_fade:
            self._fade_in(target_vol)
        self._refresh_cue_buttons()

    def _fade_in(self, target: float = None, duration_ms: int = 1200):
        if target is None:
            target = self._engine._volume
        self._engine.set_volume(0.0)
        self._fade_target  = target
        self._fade_steps   = 30
        self._fade_step    = 0
        if not hasattr(self, '_fade_timer'):
            self._fade_timer = QTimer(self)
            self._fade_timer.timeout.connect(self._do_fade_step)
        self._fade_timer.start(duration_ms // self._fade_steps)

    def _do_fade_step(self):
        self._fade_step += 1
        v = self._fade_target * (self._fade_step / self._fade_steps)
        self._engine.set_volume(min(v, self._fade_target))
        if self._fade_step >= self._fade_steps:
            self._fade_timer.stop()
            self._engine.set_volume(self._fade_target)

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
                        font-size:17px;
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
                        font-size:17px;
                        font-weight:bold;
                    }}
                    QPushButton:hover{{
                        background:{C['hover']};
                        color:{C['text']};
                        border:1px solid {C['accent']};
                    }}
                """)

    def _set_grid_layout(self, cols: int, rows: int):
        if cols == self._grid_cols and rows == self._grid_rows:
            return
        # salva dados atuais
        saved = [p.to_dict() for p in self._pages]
        cur_idx = self._stack.currentIndex()

        # remove páginas antigas
        for page in self._pages:
            self._stack.removeWidget(page)
            page.deleteLater()
        self._pages.clear()

        self._grid_cols = cols
        self._grid_rows = rows

        # recria páginas com novo layout
        for i in range(8):
            page = TabPage(i, cols, rows)
            page.sig_play.connect(self._play)
            page.sig_cue.connect(self._on_cue)
            page.sig_focus.connect(self._on_focus)
            self._pages.append(page)
            self._stack.addWidget(page)
            if i < len(saved):
                page.from_dict(saved[i])

        self._stack.setCurrentIndex(cur_idx)
        self._update_tab_btns(cur_idx)

        # atualiza aparência dos botões de layout
        for b in self._layout_btns:
            b.setChecked(b.text() == f'{cols}×{rows}')

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
        for pg in self._pages:
            pg.set_playing(path)
        self._refresh_cue_buttons()

    def _stop(self):
        self._engine.stop()
        self._current = None
        for pg in self._pages:
            pg.set_playing(None)
        self._refresh_cue_buttons()

    def _on_pos(self, frac: float):
        self._transport.set_pos(frac, self._engine.pos_seconds())

    def _on_vu(self, l: float, r: float):
        self._vu_l.set_level(l)
        self._vu_r.set_level(r)
        self._hvu_l.set_level(l)
        self._hvu_r.set_level(r)

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
            repeat = self._cur_panel._repeat
            songs  = self._cur_panel._songs

            if repeat == 1:                        # repeat one
                self._play(songs[self._cur_row])
                self._cur_panel._list.setCurrentRow(self._cur_row)
                return

            next_row = self._cur_row + 1
            if next_row < len(songs):              # advance normally
                self._play(songs[next_row])
                self._cur_panel._list.setCurrentRow(next_row)
                self._cur_panel._list.scrollToItem(self._cur_panel._list.item(next_row))
                return

            if repeat == 2 and songs:              # repeat all — volta ao início
                self._play(songs[0])
                self._cur_panel._list.setCurrentRow(0)
                self._cur_panel._list.scrollToItem(self._cur_panel._list.item(0))
                return

        self._current   = None
        self._cur_panel = None
        self._cur_row   = -1
        for pg in self._pages:
            pg.set_playing(None)
        self._refresh_cue_buttons()

    def _open_settings(self):
        dlg = SettingsDialog(
            devices=self._cue_engine.get_devices(),
            main_device=self._main_device,
            cue_device=self._cue_device,
            music_folder=self._music_folder,
            parent=self,
        )
        if dlg.exec():
            self._main_device  = dlg.main_device()
            self._cue_device   = dlg.cue_device()
            new_folder         = dlg.music_folder()
            self._cue_engine.set_device(self._cue_device)
            if new_folder != self._music_folder:
                self._music_folder = new_folder
                self._refresh_search_btn()
                if self._search_dlg:
                    self._search_dlg.set_folder(new_folder)

    def _refresh_search_btn(self):
        has_folder = bool(self._music_folder and Path(self._music_folder).is_dir())
        self._btn_search.setEnabled(has_folder)
        self._btn_search.setToolTip(
            'Buscar música na biblioteca' if has_folder
            else 'Configure a pasta de músicas em ⚙ CONFIG. para habilitar')

    def _open_search(self):
        if not self._search_dlg:
            self._search_dlg = MusicSearchDialog(self._music_folder, parent=self)
            self._search_dlg.sig_play.connect(self._play)
            self._search_dlg.sig_add.connect(self._add_search_result)
        # atualiza nomes das playlists (podem ter sido renomeadas)
        all_panels = [p for pg in self._pages for p in pg.get_panels()]
        self._search_dlg.set_playlists([p._name for p in all_panels])
        self._search_dlg.show()
        self._search_dlg.raise_()
        self._search_dlg.activateWindow()

    def _add_search_result(self, path: str, panel_idx: int):
        all_panels = [p for pg in self._pages for p in pg.get_panels()]
        if 0 <= panel_idx < len(all_panels):
            all_panels[panel_idx].add_song(path)

    def _on_cue(self, path: str):
        self._cue_engine.set_device(self._cue_device)
        self._cue_window.load(path)
        self._cue_window.show()
        self._cue_window.raise_()

    # ── persistence ───────────────────────────────────────────────────────
    def _save(self):
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        cue_to_save = {
            path: slots
            for path, slots in CUE_POINTS.items()
            if any(v is not None for v in slots)
        }
        fadein_to_save = {
            path: flags
            for path, flags in CUE_FADEIN.items()
            if path in cue_to_save and not all(flags)
        }
        data = {
            'playlists': [pg.to_dict() for pg in self._pages],
            'settings': {
                'main_device':  self._main_device,
                'cue_device':   self._cue_device,
                'music_folder': self._music_folder,
                'grid_cols':    self._grid_cols,
                'grid_rows':    self._grid_rows,
            },
            'cue_points':  cue_to_save,
            'cue_fadein':  fadein_to_save,
        }
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self):
        if not DATA_FILE.exists():
            return
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                raw = json.load(f)

            # suporte ao formato antigo (lista directa)
            if isinstance(raw, list):
                playlists, settings = raw, {}
            else:
                playlists = raw.get('playlists', [])
                settings  = raw.get('settings', {})

            for i, pd in enumerate(playlists[:len(self._pages)]):
                self._pages[i].from_dict(pd)

            # restaura dispositivos e pasta
            self._main_device  = settings.get('main_device', '')
            self._cue_device   = settings.get('cue_device', '')
            self._music_folder = settings.get('music_folder', '')
            if self._cue_device:
                self._cue_engine.set_device(self._cue_device)
            self._refresh_search_btn()

            # restaura CUE points
            cue_data = raw.get('cue_points', {}) if isinstance(raw, dict) else {}
            for path, slots in cue_data.items():
                if isinstance(slots, list):
                    normalized = [(float(v) if v is not None else None) for v in slots]
                    CUE_POINTS[path] = (normalized + [None]*5)[:5]

            # restaura flags de fade-in (ausente = todos True por padrão)
            fadein_data = raw.get('cue_fadein', {}) if isinstance(raw, dict) else {}
            for path, flags in fadein_data.items():
                if isinstance(flags, list):
                    normalized_fi = [bool(v) for v in flags]
                    CUE_FADEIN[path] = (normalized_fi + [True]*5)[:5]

            # restaura layout de grid
            cols = settings.get('grid_cols', 3)
            rows = settings.get('grid_rows', 3)
            if (cols, rows) != (self._grid_cols, self._grid_rows):
                self._set_grid_layout(cols, rows)
                # recarrega playlists com o novo layout
                for i, pd in enumerate(playlists[:len(self._pages)]):
                    self._pages[i].from_dict(pd)

        except Exception as e:
            print(f"load data: {e}")

    def closeEvent(self, ev):
        self._save()
        self._engine.stop()
        self._cue_engine.stop()
        if HAS_PYGAME:
            pygame.quit()
        ev.accept()


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    if not HAS_PYGAME:
        print("AVISO: pygame não encontrado. Execute: pip install pygame")
    if not HAS_MUTAGEN:
        print("AVISO: mutagen não encontrado. Execute: pip install mutagen")
    if not HAS_SD:
        print("AVISO: sounddevice não encontrado. Execute: pip install sounddevice")
    if not HAS_SF:
        print("AVISO: soundfile não encontrado (necessário para CUE). Execute: pip install soundfile")

    app = QApplication(sys.argv)
    app.setApplicationName('DJ Mix Player')

    _base = Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else Path(__file__).parent
    _fonts_dir = _base / 'fonts' / 'static'
    for _ttf in _fonts_dir.glob('*.ttf'):
        QFontDatabase.addApplicationFont(str(_ttf))

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

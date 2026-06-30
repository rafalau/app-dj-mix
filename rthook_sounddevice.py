import sys, os, glob, ctypes.util as _ctutil

# ── GTK modules fix (before pygame/Qt load GTK) ──────────────────────────────
os.environ['GTK_MODULES'] = ''
os.environ['GTK3_MODULES'] = ''

# Suprime "Failed to load module" do GLib/GTK antes do GTK inicializar.
# Cinnamon seta canberra-gtk-module via Xsettings — GTK_MODULES='' não basta.
try:
    import ctypes as _ctypes
    _glib = _ctypes.CDLL('libglib-2.0.so.0')
    _G_LOG_LEVEL_MESSAGE = 1 << 5  # 32

    _LogFunc = _ctypes.CFUNCTYPE(
        None,
        _ctypes.c_char_p,   # log_domain
        _ctypes.c_int,      # log_level
        _ctypes.c_char_p,   # message
        _ctypes.c_void_p,   # user_data
    )

    @_LogFunc
    def _gtk_msg_filter(domain, level, message, user_data):
        if message and b'Failed to load module' in message:
            return  # suprime apenas este aviso
        _glib.g_log_default_handler(domain, level, message, None)

    _glib.g_log_set_handler(b'Gtk', _G_LOG_LEVEL_MESSAGE, _gtk_msg_filter, None)
except Exception:
    pass

# ── find_library patch para libs bundled ─────────────────────────────────────
_lib_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))

_orig_find_library = _ctutil.find_library

def _patched_find_library(name):
    result = _orig_find_library(name)
    if result is not None:
        return result
    for path in glob.glob(os.path.join(_lib_dir, f'lib{name}.*')):
        return path
    return None

_ctutil.find_library = _patched_find_library

# ── Debug log (Flatpak) ───────────────────────────────────────────────────────
try:
    _log = os.path.join(os.path.expanduser('~'), 'djmix_debug.log')
    with open(_log, 'w') as _f:
        _f.write(f'lib_dir: {_lib_dir}\n')
        _f.write(f'find_library(portaudio): {_patched_find_library("portaudio")}\n')
        _f.write(f'find_library(pulse): {_patched_find_library("pulse")}\n')
        try:
            import pulsectl
            _f.write('pulsectl: importado OK\n')
            with pulsectl.Pulse('djmix-debug') as _p:
                _sinks = _p.sink_list()
                _f.write(f'pulsectl sinks ({len(_sinks)}):\n')
                for _s in _sinks:
                    _f.write(f'  {_s.name} | {_s.description}\n')
                    for _port in _s.port_list:
                        _f.write(f'    port: {_port.description} | avail={_port.available}\n')
        except Exception as _e:
            _f.write(f'pulsectl ERRO: {_e}\n')
        try:
            import sounddevice as _sd
            _devs = list(_sd.query_devices())
            _f.write(f'sd.query_devices ({len(_devs)}):\n')
            for _i, _d in enumerate(_devs):
                if _d['max_output_channels'] > 0:
                    _f.write(f'  [{_i}] {_d["name"]} (out={_d["max_output_channels"]})\n')
        except Exception as _e:
            _f.write(f'sd.query_devices ERRO: {_e}\n')
except Exception:
    pass

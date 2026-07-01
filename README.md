# DJ Mix Player

Player de playlists para DJs com múltiplos painéis, sonoplastia, VU meters, CUE points e seleção de saída de áudio.

**Autor:** Rafael Lauriano · **Versão:** 1.0.7 · **Licença:** MIT (open source, gratuito)

---

## Download

👉 **[Baixar na página de releases](https://github.com/rafalau/app-dj-mix/releases/latest)**

| Sistema | Arquivo |
|---------|---------|
| Windows | `DJMixPlayer_Setup_v1.0.7.exe` |
| Linux (Debian/Ubuntu) | `djmixplayer_1.0.7_amd64.deb` |

### Instalação Windows
Execute `DJMixPlayer_Setup_v1.0.7.exe` e siga o assistente — não precisa instalar Python.

### Instalação Linux (Debian/Ubuntu)
```bash
sudo dpkg -i djmixplayer_1.0.7_amd64.deb
sudo apt-get install -f   # instala dependências se necessário
```
Após instalar, procure **DJ Mix Player** no menu de aplicativos.

---

## Funcionalidades

- **8 abas** com playlists em grade configurável (3×3, 4×3, 2×1…)
- **Sonoplastia** — 50 slots de SFX com atalhos numéricos, drag & drop e pré-escuta
- **CUE points** — 5 pontos por música com fade-in opcional
- **VU meters** L/R com peak hold
- **Pré-escuta** em dispositivo de áudio separado
- **Auto-update** — o app avisa quando há nova versão disponível
- **Exportar / importar** configurações (backup)
- **Busca** em tempo real em todas as playlists
- Drag & drop de arquivos e pastas
- Playlists salvas automaticamente em `~/.djmixplayer/playlists.json`

### Formatos de áudio suportados
`.mp3` `.wav` `.flac` `.ogg` `.aac` `.m4a` `.wma` `.opus` `.mp2` `.mp4`

### Atalhos de teclado
| Tecla | Ação |
|-------|------|
| `Espaço` | Play / Pause |
| `← →` | Retroceder / Avançar 2s |
| `F1 – F5` | CUE 1–5 |
| `Ctrl+F` | Buscar música |
| `Ctrl+1–9` | Focar playlist 1–9 |
| `Ctrl+Alt+0/1/2` | Focar playlist 10/11/12 |
| `Alt+1–8` | Mudar de aba |

---

## Rodar pelo código-fonte

### Pré-requisitos
- Python 3.12+
- `pip install -r requirements.txt`

### Windows
```cmd
pip install -r requirements.txt
python main.py
```

### Linux
```bash
pip3 install -r requirements.txt
python3 main.py
```

---

## Build

### Windows
1. Instale o [Inno Setup](https://jrsoftware.org/isinfo.php)
2. Execute `build_windows.bat`
3. O instalador aparece em `dist/`

### Linux (.deb)
```bash
bash build_deb.sh
# Gera: dist/djmixplayer_X.X.X_amd64.deb
```

---

## Estrutura

```
app-dj-mix/
├── main.py                  # App completo
├── version.py               # Versão e metadados
├── updater.py               # Verificador de atualizações
├── requirements.txt
├── djmix_linux.spec         # PyInstaller (Linux)
├── djmix_windows.spec       # PyInstaller (Windows)
├── build_deb.sh             # Build .deb (Linux)
├── build_windows.bat        # Build installer (Windows)
├── assets/
├── fonts/
└── packaging/
    ├── deb/                 # Metadados do pacote .deb
    └── windows/             # Script Inno Setup
```

# DJ Mix Player

Player de playlists para DJs com múltiplos painéis, VU meters, controles de transporte e seleção de saída de áudio.

Funciona em **Windows** e **Linux**.

---

## Dependências

| Pacote | Versão mínima | Para quê |
|--------|--------------|----------|
| PyQt6 | 6.4.0 | Interface gráfica |
| pygame | 2.1.0 | Reprodução de áudio (MP3, WAV, FLAC, OGG, WMA) |
| mutagen | 1.46.0 | Leitura de metadados (artista, título, duração) |
| sounddevice | 0.4.6 | Listagem de dispositivos de saída de áudio |
| numpy | 1.23.0 | Cálculos dos VU meters |

### Formatos de áudio suportados
`.mp3` `.wav` `.flac` `.ogg` `.aac` `.m4a` `.wma` `.opus`

---

## Instalação e execução

### Windows

**1. Instalar Python 3.12+**

Baixe em https://www.python.org/downloads/  
Na instalação marque obrigatoriamente: **"Add python.exe to PATH"**

**2. Instalar dependências**

```cmd
pip install PyQt6 pygame mutagen sounddevice numpy
```

Ou dê duplo clique em `instalar.bat`.

**3. Rodar**

```cmd
python main.py
```

Se `python` não for reconhecido (conflito com Microsoft Store):

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" main.py
```

---

### Linux (Ubuntu / Debian / Mint)

**1. Instalar Python e pip**

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv
```

**2. Instalar dependências de sistema** (necessárias para pygame e áudio)

```bash
sudo apt install libsdl2-dev libsdl2-mixer-dev libportaudio2 ffmpeg
```

Para Fedora / RHEL:
```bash
sudo dnf install SDL2 SDL2_mixer portaudio ffmpeg
```

Para Arch:
```bash
sudo pacman -S sdl2 sdl2_mixer portaudio ffmpeg
```

**3. Instalar dependências Python**

```bash
pip3 install PyQt6 pygame mutagen sounddevice numpy
```

Ou com ambiente virtual (recomendado):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install PyQt6 pygame mutagen sounddevice numpy
```

**4. Rodar**

```bash
python3 main.py
```

Com venv:
```bash
source .venv/bin/activate
python main.py
```

---

## Funcionalidades

- **5 abas** laterais (1–5), cada uma com **9 playlists** em grade 3×3
- **Adicionar músicas** por arquivo, pasta ou drag & drop
- **Campo de busca** — filtra em todas as playlists simultaneamente
- **Renomear playlist** — duplo clique no título ou botão ✎
- **Autoplay** — ao terminar uma música passa automaticamente para a próxima
- **VU meters** L/R com peak hold
- **Seleção de saída de áudio** (placa de som)
- **Playlists salvas** automaticamente em `~/.djmixplayer/playlists.json`
- **Teclado:**
  - `Enter` — toca a música selecionada
  - `Tab / Shift+Tab` — navega entre playlists
  - `↑ ↓` — navega dentro da playlist

---

## Estrutura

```
app-dj-mix/
├── main.py          # Aplicação completa
├── requirements.txt # Dependências
├── instalar.bat     # Instalador Windows
└── instalar.sh      # Instalador Linux/macOS
```

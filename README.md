# DJ Mix Player

Player de playlists para DJs com múltiplos painéis, sonoplastia, VU meters, CUE points e seleção de saída de áudio.

**Autor:** Rafael Lauriano · **Versão:** 1.0.0 · **Licença:** MIT (open source, gratuito)

---

## Download

👉 **[Baixar instalador Windows](https://github.com/rafalau/app-dj-mix/releases/latest)**

Baixe `DJMixPlayer_Setup_vX.X.X.exe`, execute e pronto — não precisa instalar Python.

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

---

## Rodar pelo código-fonte

### Pré-requisitos
- Python 3.12+
- Dependências: `pip install -r requirements.txt`

### Windows
```cmd
pip install -r requirements.txt
python main.py
```
Ou dê duplo clique em `instalar.bat`.

### Linux
```bash
pip3 install -r requirements.txt
python3 main.py
```

---

## Build do instalador (Windows)

### Automático (GitHub Actions)
Crie uma tag e o instalador é gerado e publicado automaticamente:
```bash
git tag v1.0.0
git push origin v1.0.0
```

### Manual
1. Instale o [Inno Setup](https://jrsoftware.org/isdl.php)
2. Execute `build_windows.bat`
3. O instalador aparece em `dist/installer/`

---

## Estrutura

```
app-dj-mix/
├── main.py                     # App completo
├── version.py                  # Versão e metadados
├── updater.py                  # Verificador de atualizações (GitHub)
├── requirements.txt
├── djmix.spec                  # PyInstaller
├── build_windows.bat           # Build local
├── assets/
│   ├── icon.ico                # Ícone gerado
│   ├── create_icon.py          # Gera o ícone
│   └── version_info.txt        # Metadados do .exe
├── installer/
│   └── DJMixPlayer.iss         # Inno Setup
├── .github/workflows/
│   └── build-release.yml       # CI/CD GitHub Actions
└── fonts/
```

---

## Configurar o repositório GitHub

1. Crie o repositório: `github.com/rafalau/djmixplayer` (público)
2. Atualize `version.py` com seu usuário GitHub se necessário
3. Push do código:
   ```bash
   git remote add origin https://github.com/rafalau/app-dj-mix.git
   git push -u origin main
   ```
4. Para publicar a v1.0.0:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
5. O GitHub Actions builda e cria o Release automaticamente (~10 min)

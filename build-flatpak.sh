#!/bin/bash
set -e

APP_ID="io.github.rafalau.DjMixPlayer"
FLATPAK_DIR="packaging/flatpak"
BUILD_DIR="build-flatpak"

echo "=== DJ Mix Player — Build Flatpak ==="

# ── 1. Dependências ──────────────────────────────────────────────────────────
echo "[1/5] Verificando dependências..."

if ! command -v flatpak-builder &>/dev/null; then
    echo "Instalando flatpak-builder..."
    sudo apt-get install -y flatpak flatpak-builder
fi

if ! flatpak remote-list | grep -q flathub; then
    echo "Adicionando repositório Flathub..."
    flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
fi

echo "Instalando runtimes Flatpak (pode demorar na primeira vez)..."
flatpak install --user -y flathub org.freedesktop.Platform//23.08 org.freedesktop.Sdk//23.08 2>/dev/null || true

# ── 2. Ambiente virtual ──────────────────────────────────────────────────────
echo "[2/5] Preparando ambiente virtual..."

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    .venv/bin/pip install -q -r requirements.txt
fi

# ── 3. PyInstaller ───────────────────────────────────────────────────────────
echo "[3/5] Gerando bundle com PyInstaller..."
.venv/bin/pyinstaller djmix_linux.spec --clean --noconfirm

if [ ! -f "dist/DJMixPlayer/DJMixPlayer" ]; then
    echo "ERRO: PyInstaller não gerou o executável."
    exit 1
fi

# ── 4. Staging dos arquivos para o Flatpak ───────────────────────────────────
echo "[4/5] Preparando arquivos para o Flatpak..."
cp -r dist/DJMixPlayer            "$FLATPAK_DIR/DJMixPlayer"
cp assets/icon_256.png            "$FLATPAK_DIR/icon_256.png"

# Inclui pw-dump no bundle para que o Flatpak enumere dispositivos via PipeWire
# (o socket /run/user/*/pipewire-0 é acessível via --filesystem=xdg-run/pipewire-0)
if [ -x "/usr/bin/pw-dump" ]; then
    cp /usr/bin/pw-dump "$FLATPAK_DIR/DJMixPlayer/_internal/pw-dump"
    chmod +x "$FLATPAK_DIR/DJMixPlayer/_internal/pw-dump"
    echo "   pw-dump bundled OK"
fi

# ── 5. Build do Flatpak ──────────────────────────────────────────────────────
echo "[5/5] Construindo Flatpak..."
flatpak-builder \
    --user \
    --install \
    --force-clean \
    "$BUILD_DIR" \
    "$FLATPAK_DIR/$APP_ID.yml"

# ── Exporta bundle .flatpak para distribuição ────────────────────────────────
echo ""
echo "Exportando $APP_ID.flatpak..."
flatpak build-bundle \
    "$HOME/.local/share/flatpak/repo" \
    "${APP_ID}.flatpak" \
    "$APP_ID"

# ── Limpeza do staging ───────────────────────────────────────────────────────
rm -rf "$FLATPAK_DIR/DJMixPlayer" "$FLATPAK_DIR/icon_256.png"

echo ""
echo "✓ Pronto! Arquivo gerado: ${APP_ID}.flatpak"
echo ""
echo "Para instalar em outro computador:"
echo "  flatpak install ${APP_ID}.flatpak"
echo ""
echo "Para testar localmente agora:"
echo "  flatpak run $APP_ID"

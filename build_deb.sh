#!/bin/bash
set -e

VERSION=$(python3 -c "from version import APP_VERSION; print(APP_VERSION)")
PKG_NAME="djmixplayer_${VERSION}_amd64"
DEB_DIR="dist/${PKG_NAME}"

echo "=== DJ Mix Player — Build .deb (v${VERSION}) ==="

# ── 1. Ambiente virtual ──────────────────────────────────────────────────────
echo "[1/4] Preparando ambiente virtual..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    .venv/bin/pip install -q -r requirements.txt
fi

# ── 2. PyInstaller ───────────────────────────────────────────────────────────
echo "[2/4] Gerando bundle com PyInstaller..."
.venv/bin/pyinstaller djmix_linux.spec --clean --noconfirm

if [ ! -f "dist/DJMixPlayer/DJMixPlayer" ]; then
    echo "ERRO: PyInstaller não gerou o executável."
    exit 1
fi

# Inclui pw-dump para enumeração nativa de dispositivos PipeWire
if [ -x "/usr/bin/pw-dump" ]; then
    cp /usr/bin/pw-dump "dist/DJMixPlayer/_internal/pw-dump"
    chmod +x "dist/DJMixPlayer/_internal/pw-dump"
    echo "   pw-dump bundled OK"
fi

# ── 3. Estrutura do pacote .deb ──────────────────────────────────────────────
echo "[3/4] Montando pacote .deb..."
rm -rf "$DEB_DIR"
mkdir -p "$DEB_DIR/DEBIAN"
mkdir -p "$DEB_DIR/opt/djmixplayer"
mkdir -p "$DEB_DIR/usr/share/applications"
mkdir -p "$DEB_DIR/usr/share/icons/hicolor/256x256/apps"

# Arquivos do app
cp -r dist/DJMixPlayer/. "$DEB_DIR/opt/djmixplayer/"
chmod +x "$DEB_DIR/opt/djmixplayer/DJMixPlayer"

# Ícone
cp assets/icon_256.png "$DEB_DIR/usr/share/icons/hicolor/256x256/apps/djmixplayer.png"

# .desktop
cp packaging/deb/djmixplayer.desktop "$DEB_DIR/usr/share/applications/djmixplayer.desktop"

# DEBIAN/control com versão atualizada
sed "s/^Version:.*/Version: ${VERSION}/" packaging/deb/control > "$DEB_DIR/DEBIAN/control"

# Permissões corretas para o DEBIAN/
chmod 755 "$DEB_DIR/DEBIAN"
chmod 644 "$DEB_DIR/DEBIAN/control"

# ── 4. Gera o .deb ──────────────────────────────────────────────────────────
echo "[4/4] Gerando ${PKG_NAME}.deb..."
dpkg-deb --build --root-owner-group "$DEB_DIR" "dist/${PKG_NAME}.deb"

echo ""
echo "✓ Pronto: dist/${PKG_NAME}.deb"
echo ""
echo "Para instalar:"
echo "  sudo dpkg -i dist/${PKG_NAME}.deb"
echo "  sudo apt-get install -f   # resolve dependências se necessário"

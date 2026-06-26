#!/bin/bash
echo "Instalando dependencias DJ Mix Player..."

# Cria o ambiente virtual se ainda não existir
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

.venv/bin/pip install PyQt6 pygame mutagen sounddevice numpy

echo ""
echo "Pronto! Para rodar: python3 main.py"

#!/bin/bash
if [ ! -d ".venv" ]; then
    echo "Ambiente virtual nao encontrado. Execute ./instalar.sh primeiro."
    exit 1
fi

.venv/bin/python3 main.py

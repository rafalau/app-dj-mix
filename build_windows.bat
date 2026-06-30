@echo off
setlocal

echo ============================================
echo   DJ Mix Player - Build para Windows
echo ============================================
echo.

:: Gera o icone
echo [1/4] Gerando icone...
py -3 assets\create_icon.py
if errorlevel 1 ( echo ERRO ao gerar icone & pause & exit /b 1 )

:: Instala dependencias de build
echo [2/4] Instalando dependencias...
py -3 -m pip install -q PyQt6 pygame mutagen sounddevice soundfile numpy pillow pyinstaller
if errorlevel 1 ( echo ERRO ao instalar dependencias & pause & exit /b 1 )

:: Builda com PyInstaller
echo [3/4] Buildando com PyInstaller...
py -3 -m PyInstaller djmix.spec --noconfirm
if errorlevel 1 ( echo ERRO no PyInstaller & pause & exit /b 1 )

:: Verifica se Inno Setup esta instalado
echo [4/4] Criando instalador...
set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
    echo.
    echo AVISO: Inno Setup nao encontrado.
    echo Baixe em: https://jrsoftware.org/isdl.php
    echo Depois execute: %ISCC% installer\DJMixPlayer.iss
    echo.
    echo O build do app esta em: dist\DJMixPlayer\
) else (
    if not exist dist\installer mkdir dist\installer
    %ISCC% installer\DJMixPlayer.iss
    if errorlevel 1 ( echo ERRO no Inno Setup & pause & exit /b 1 )
    echo.
    echo ============================================
    echo   INSTALADOR GERADO:
    echo   dist\installer\DJMixPlayer_Setup_v1.0.4.exe
    echo ============================================
)

echo.
pause

@echo off
setlocal
echo === DJ Mix Player — Build Windows ===

:: ── 1. Instala dependencias ──────────────────────────────────────────────────
echo [1/4] Instalando dependencias...
py -3 -m pip install -q -r requirements.txt
if errorlevel 1 ( echo ERRO ao instalar dependencias & pause & exit /b 1 )

:: ── 2. PyInstaller ───────────────────────────────────────────────────────────
echo [2/4] Empacotando com PyInstaller...
py -3 -m PyInstaller djmix_windows.spec --clean --noconfirm
if errorlevel 1 ( echo ERRO no PyInstaller & pause & exit /b 1 )

if not exist "dist\DJMixPlayer\DJMixPlayer.exe" (
    echo ERRO: executavel nao gerado.
    pause & exit /b 1
)
echo     OK: dist\DJMixPlayer\DJMixPlayer.exe

:: ── 3. Inno Setup ────────────────────────────────────────────────────────────
echo [3/4] Gerando installer...

set ISCC=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe"       set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"

if "%ISCC%"=="" (
    echo AVISO: Inno Setup nao encontrado.
    echo        Baixe em: https://jrsoftware.org/isinfo.php
    echo        Depois rode: ISCC packaging\windows\installer.iss
    echo.
    echo Build concluido sem installer. Executavel em: dist\DJMixPlayer\
    goto :done
)

%ISCC% packaging\windows\installer.iss
if errorlevel 1 ( echo ERRO no Inno Setup & pause & exit /b 1 )

:: ── 4. Upload GitHub ─────────────────────────────────────────────────────────
echo [4/4] Fazendo upload para o GitHub...
where gh >nul 2>&1
if errorlevel 1 (
    echo AVISO: gh CLI nao encontrado.
    echo        Instale em: https://cli.github.com
    echo        Depois rode: gh release upload v1.0.8 dist\DJMixPlayer_Setup_v1.0.8.exe --repo rafalau/app-dj-mix --clobber
    goto :done
)

gh release upload v1.0.8 "dist\DJMixPlayer_Setup_v1.0.8.exe" --repo rafalau/app-dj-mix --clobber
if errorlevel 1 ( echo ERRO no upload & pause & exit /b 1 )
echo Upload concluido!

:done
echo.
echo === Pronto! ===
pause

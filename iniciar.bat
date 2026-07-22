@echo off
title Oga Pora - Sistema de Gestion Comercial
echo.
echo ===========================================================
echo            OGA PORA - Sistema de Gestion Comercial
echo                    Iniciando el sistema...
echo ===========================================================
echo.

if not exist "backend\venv\Scripts\activate.bat" (
    echo  ERROR: El sistema no esta instalado.
    echo  Ejecutar primero: setup.bat
    echo.
    pause
    exit /b 1
)

echo  [1/2] Iniciando el servidor (backend)...
start "Oga Pora - Servidor" cmd /k "cd /d %~dp0backend && venv\Scripts\activate && daphne -b 0.0.0.0 -p 8000 config.asgi:application"
timeout /t 4 /nobreak >nul

echo  [2/2] Iniciando la interfaz (frontend)...
start "Oga Pora - Interfaz" cmd /k "cd /d %~dp0frontend && npm run dev"
timeout /t 5 /nobreak >nul

echo.
echo ===========================================================
echo   Sistema iniciado.
echo.
echo   En esta computadora:   http://localhost:5173
echo   Desde las tablets:     http://[IP-DE-ESTA-PC]:5173
echo.
echo   Para saber la IP, abrir otra ventana y escribir: ipconfig
echo   (buscar "Direccion IPv4", ej: 192.168.0.10)
echo.
echo   NO CERRAR las dos ventanas negras que se abrieron:
echo   son el servidor y la interfaz. Si las cierra, el
echo   sistema deja de funcionar.
echo ===========================================================
echo.
echo  Abriendo el navegador...
timeout /t 2 /nobreak >nul
start http://localhost:5173
echo.
pause

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

rem  Dos endpoints, IPv4 e IPv6: los nombres de red (OGAPORA, ogapora.local)
rem  resuelven PRIMERO a IPv6, asi que escuchando solo en 0.0.0.0 el navegador
rem  intenta IPv6, no encuentra a nadie y da timeout. Los "\:\:" van escapados
rem  porque twisted usa ":" para separar los campos del endpoint.
echo  [1/2] Iniciando el servidor (backend)...
start "Oga Pora - Servidor" cmd /k "cd /d %~dp0backend && venv\Scripts\activate && daphne -e tcp:8000:interface=0.0.0.0 -e tcp6:8000:interface=\:\: config.asgi:application"
timeout /t 4 /nobreak >nul

echo  [2/2] Iniciando la interfaz (frontend)...
start "Oga Pora - Interfaz" cmd /k "cd /d %~dp0frontend && npm run dev"
timeout /t 5 /nobreak >nul

echo.
echo ===========================================================
echo   Sistema iniciado.
echo.
echo   En esta computadora:   http://localhost:5173
echo   Desde otra PC:         http://%COMPUTERNAME%:5173
echo   Desde las tablets:     http://[IP-DE-ESTA-PC]:5173
echo.
echo   Las tablets Android no resuelven nombres de red: ahi hay que usar
echo   la IP la primera vez. Despues la app se acuerda sola y, si la IP
echo   cambia, vuelve a buscar el servidor. Ver docs\descubrimiento_red.md
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

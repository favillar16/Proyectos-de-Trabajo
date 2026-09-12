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

rem  Los dos arrancan ocultos, sin ventana propia: si quedaran visibles el
rem  personal del local podria cerrarlos por accidente creyendo que son una
rem  ventana cualquiera, y el sistema se cae para todas las tablets a la vez.
rem  La logica vive en iniciar_servicios.ps1 (ahi esta tambien la nota sobre
rem  IPv4/IPv6). El PID de cada uno queda en logs\*.pid para que detener.bat
rem  sepa a cual parar.
echo  [1/2] Iniciando el servidor (backend)...
echo  [2/2] Iniciando la interfaz (frontend)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0iniciar_servicios.ps1"
timeout /t 6 /nobreak >nul

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
echo   El servidor y la interfaz corren ocultos, sin ventana visible, para
echo   que no se puedan cerrar por accidente. Para pararlos: detener.bat
echo   Registros: logs\daphne.log y logs\vite.log
echo ===========================================================
echo.
echo  Abriendo el navegador...
timeout /t 2 /nobreak >nul
start http://localhost:5173
echo.
pause

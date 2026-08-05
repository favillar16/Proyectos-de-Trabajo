@echo off
title Oga Pora - Instalar sync de la notebook
echo.
echo ===========================================================
echo   Instalando la sincronizacion automatica con el servidor
echo ===========================================================
echo.

if not exist "%~dp0config.env" (
    echo  ERROR: falta el archivo config.env en esta carpeta.
    echo  Copiar config.env.example como config.env y completarlo
    echo  con los datos del servidor antes de instalar la tarea.
    echo.
    pause
    exit /b 1
)

echo  Se va a registrar una tarea de Windows que corre cada 5 minutos
echo  y sincroniza los datos SOLO cuando esta notebook esta conectada
echo  a la red del local. Fuera del local, no hace nada.
echo.

schtasks /create /tn "OgaPora - Sync Notebook" ^
    /tr "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"%~dp0sync_notebook.ps1\"" ^
    /sc minute /mo 5 /f

if %errorlevel% neq 0 (
    echo.
    echo  ERROR al crear la tarea programada. Revisar el mensaje de arriba.
    pause
    exit /b 1
)

echo.
echo ===========================================================
echo   Listo. La tarea "OgaPora - Sync Notebook" quedo instalada.
echo.
echo   Para probarla ahora mismo:
echo     schtasks /run /tn "OgaPora - Sync Notebook"
echo.
echo   Para desinstalarla:
echo     schtasks /delete /tn "OgaPora - Sync Notebook" /f
echo.
echo   Los registros de cada corrida quedan en la carpeta "logs"
echo   y el estado de la ultima sincronizacion en "estado".
echo ===========================================================
echo.
pause

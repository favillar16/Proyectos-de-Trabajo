@echo off
rem ==========================================================================
rem  Oga Pora - para el servidor y la interfaz que corren ocultos en segundo
rem  plano (los que levanta iniciar.bat). Usar esto antes de un mantenimiento
rem  o para reiniciar el sistema despues de cambiar la configuracion (.env).
rem  Doble clic.
rem ==========================================================================
title Oga Pora - Deteniendo el sistema
echo.
echo ===========================================================
echo            OGA PORA - Deteniendo el sistema
echo ===========================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0detener_servicios.ps1"
echo.
echo ===========================================================
echo   Listo. Para volver a arrancar el sistema: iniciar.bat
echo ===========================================================
echo.
pause

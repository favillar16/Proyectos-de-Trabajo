@echo off
:: Respaldo completo del sistema: base de datos + fotos de productos.
::
::   respaldo.bat              guarda en ..\respaldos\
::   respaldo.bat D:\          guarda en un pendrive
::
:: Se puede correr con el sistema andando, no molesta a nadie.
title Oga Pora - Respaldo del sistema
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0respaldo.ps1" %*
echo.
pause

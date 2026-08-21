@echo off
:: Restaura un respaldo en ESTA computadora.
::
::   restaurar.bat                                 usa el respaldo mas nuevo de ..\respaldos\
::   restaurar.bat D:\respaldo_20260820_143000     usa uno puntual
::
:: ATENCION: borra y reemplaza la base de datos de esta PC. Cerrar antes el
:: sistema (las dos ventanas negras de iniciar.bat). Pide confirmacion.
title Oga Pora - Restaurar respaldo
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restaurar.ps1" %*
echo.
pause

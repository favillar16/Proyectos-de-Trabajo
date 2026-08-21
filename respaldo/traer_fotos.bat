@echo off
:: Trae las fotos de productos desde el repositorio de git. Se corre en la
:: PC SERVIDOR, despues de subir_fotos.bat en el equipo de armado.
::
:: No hace falta si el proyecto se clono con "git clone": el clone ya las trae.
title Oga Pora - Traer fotos desde el repositorio
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0traer_fotos.ps1" %*
echo.
pause

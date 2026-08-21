@echo off
:: Sube las fotos de productos al repositorio de git, para trasladarlas a la
:: PC servidor sin pendrive. Se corre en el EQUIPO DE ARMADO (el que tiene
:: las fotos).
::
:: OJO: esto mueve las fotos, NO la base de datos. El repositorio es publico
:: y la base lleva datos de clientes y contrasenas. Ver
:: docs\respaldo_y_migracion.md seccion 3.5.
title Oga Pora - Subir fotos al repositorio
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0subir_fotos.ps1" %*
echo.
pause

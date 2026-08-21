@echo off
rem ==========================================================================
rem  Oga Pora - deja la PC servidor lista para la red del local.
rem  Doble clic. Va a pedir permiso de Administrador (decir "Si").
rem ==========================================================================
powershell -NoProfile -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','\"%~dp0preparar_red.ps1\"'"

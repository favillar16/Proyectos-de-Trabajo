@echo off
rem ==========================================================================
rem  Oga Pora - crea el rol de solo lectura "notebook_sync" en la PC servidor.
rem  Doble clic. Va a pedir permiso de Administrador (decir "Si").
rem
rem  La contrasena se genera sola y queda en credenciales_sync.txt, en esta
rem  misma carpeta, lista para pegar en el config.env de la notebook.
rem ==========================================================================
powershell -NoProfile -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','\"%~dp0crear_rol_sync.ps1\"'"

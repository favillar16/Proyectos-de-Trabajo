@echo off
rem ==========================================================================
rem  Oga Pora - deja PostgreSQL listo en la PC servidor:
rem    - le pone contrasena conocida al superusuario "postgres"
rem    - crea el rol de solo lectura "notebook_sync" que usa el sync
rem
rem  Las dos contrasenas salen de credenciales_servidor.txt (esta carpeta).
rem  Doble clic. Va a pedir permiso de Administrador (decir "Si").
rem ==========================================================================
powershell -NoProfile -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','\"%~dp0configurar_postgres.ps1\"'"

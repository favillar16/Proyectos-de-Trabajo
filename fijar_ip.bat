@echo off
rem ==========================================================================
rem  Oga Pora - le pone IP fija a la PC servidor, sin depender del router.
rem  Doble clic. Va a pedir permiso de Administrador (decir "Si").
rem
rem  Para volver a DHCP:  fijar_ip.bat deshacer
rem ==========================================================================
if /i "%~1"=="deshacer" (
    powershell -NoProfile -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','\"%~dp0fijar_ip.ps1\"','-Deshacer'"
    exit /b
)
powershell -NoProfile -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','\"%~dp0fijar_ip.ps1\"'"

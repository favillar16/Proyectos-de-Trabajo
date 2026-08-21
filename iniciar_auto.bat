@echo off
rem ==========================================================================
rem  Oga Pora - arranque automatico al prender la PC servidor.
rem
rem  Lo llama el acceso directo de la carpeta de Inicio de Windows. No es para
rem  usarlo a mano: para arrancar el sistema a proposito esta iniciar.bat.
rem
rem  Lo unico que agrega sobre iniciar.bat es esperar a que PostgreSQL acepte
rem  conexiones. Al prender la PC, el servicio de PostgreSQL y este script
rem  arrancan casi al mismo tiempo, y si el backend se adelanta la primera
rem  pantalla del sistema sale con error de base de datos.
rem ==========================================================================

set PGISREADY=C:\Program Files\PostgreSQL\15\bin\pg_isready.exe

echo.
echo  Oga Pora - arranque automatico
echo  Esperando a que PostgreSQL este listo...
echo.

if not exist "%PGISREADY%" (
    echo  No se encontro pg_isready, se espera 20 segundos y se sigue igual.
    timeout /t 20 /nobreak >nul
    goto arrancar
)

rem 30 intentos de 2 segundos = hasta 1 minuto de espera
for /l %%i in (1,1,30) do (
    "%PGISREADY%" -h localhost -p 5432 -q
    if not errorlevel 1 (
        echo  PostgreSQL listo.
        goto arrancar
    )
    timeout /t 2 /nobreak >nul
)

echo  PostgreSQL no respondio en 1 minuto. Se arranca igual: si el sistema
echo  muestra error de base de datos, revisar el servicio postgresql-x64-15.

:arrancar
call "%~dp0iniciar.bat"

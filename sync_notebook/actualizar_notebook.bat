@echo off
setlocal enabledelayedexpansion
title Oga Pora - Actualizar base de datos de la notebook
echo.
echo ===========================================================
echo   OGA PORA - Actualizar base de datos local (notebook)
echo ===========================================================
echo.
echo  Trae la version mas reciente de los datos y de la estructura
echo  de la base del servidor y la aplica ACA, reemplazando por
echo  completo la base local (es un espejo de solo lectura).
echo.
echo  Se puede correr en cualquier momento, las veces que haga
echo  falta - por ejemplo, despues de instalar una actualizacion
echo  del sistema en el servidor. Requiere estar conectado a la
echo  misma red WiFi que la PC servidor del local.
echo.

set "CARPETA=%~dp0"
set "CONFIG=%CARPETA%config.env"
set "TMPDIR=%CARPETA%tmp"
if not exist "%TMPDIR%" mkdir "%TMPDIR%"

if not exist "%CONFIG%" (
    echo  ERROR: no se encontro config.env en esta carpeta.
    echo  Copiar config.env.example como config.env y completarlo
    echo  segun docs\sync_notebook.md antes de usar esta herramienta.
    echo.
    pause
    exit /b 1
)

echo [1/5] Leyendo configuracion...
for /f "usebackq tokens=1,2 delims==" %%A in ("%CONFIG%") do (
    set "CLAVE=%%A"
    if not "!CLAVE:~0,1!"=="#" if not "%%A"=="" (
        set "%%A=%%B"
    )
)

if defined PG_BIN_DIR (
    set "PGDUMP=%PG_BIN_DIR%\pg_dump.exe"
    set "PSQL=%PG_BIN_DIR%\psql.exe"
) else (
    set "PGDUMP=pg_dump"
    set "PSQL=psql"
)
echo   OK
echo.

echo [2/5] Descargando datos del servidor (%SERVIDOR_HOST%)...
set "DUMP=%TEMP%\ceramica_dump_%RANDOM%.sql"
set "PGPASSWORD=%SERVIDOR_DB_PASSWORD%"
"%PGDUMP%" --host=%SERVIDOR_HOST% --port=%SERVIDOR_DB_PUERTO% --username=%SERVIDOR_DB_USUARIO% --dbname=%SERVIDOR_DB_NOMBRE% --clean --if-exists --no-owner --no-privileges --file="%DUMP%" >"%TMPDIR%\ultimo_dump.log" 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  ERROR: no se pudo conectar al servidor o descargar los datos.
    echo  Verificar que esta compu este conectada a la misma red WiFi
    echo  que el servidor, y que SERVIDOR_HOST en config.env sea
    echo  correcto. Detalle en tmp\ultimo_dump.log
    set "PGPASSWORD="
    echo.
    pause
    exit /b 1
)
echo   OK
echo.

echo [3/5] Recreando la base de datos local desde cero...
echo  (esto evita que queden tablas viejas de versiones anteriores
echo   del sistema que ya no existen en el servidor)
set "PGPASSWORD=%LOCAL_DB_PASSWORD%"
"%PSQL%" --host=localhost --port=%LOCAL_DB_PUERTO% --username=%LOCAL_DB_USUARIO% --dbname=postgres --set=ON_ERROR_STOP=1 --quiet --command="DROP DATABASE IF EXISTS %LOCAL_DB_NOMBRE% WITH (FORCE);" --command="CREATE DATABASE %LOCAL_DB_NOMBRE% OWNER %LOCAL_DB_USUARIO%;" >"%TMPDIR%\ultimo_recreate.log" 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  ERROR: no se pudo recrear la base local.
    echo  Revisar que el usuario %LOCAL_DB_USUARIO% tenga el permiso
    echo  CREATEDB en Postgres ^(ver docs\sync_notebook.md^). Se puede
    echo  otorgar una vez, como superusuario:
    echo    ALTER ROLE %LOCAL_DB_USUARIO% CREATEDB;
    echo  Detalle en tmp\ultimo_recreate.log
    del "%DUMP%" >nul 2>&1
    set "PGPASSWORD="
    echo.
    pause
    exit /b 1
)
echo   OK
echo.

echo [4/5] Aplicando los datos del servidor...
"%PSQL%" --host=localhost --port=%LOCAL_DB_PUERTO% --username=%LOCAL_DB_USUARIO% --dbname=%LOCAL_DB_NOMBRE% --set=ON_ERROR_STOP=1 --quiet --file="%DUMP%" >"%TMPDIR%\ultimo_restore.log" 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  ERROR: la restauracion fallo. Revisar el detalle en
    echo  tmp\ultimo_restore.log
    del "%DUMP%" >nul 2>&1
    set "PGPASSWORD="
    echo.
    pause
    exit /b 1
)
set "PGPASSWORD="
echo   OK
echo.

echo [5/5] Limpiando archivos temporales...
del "%DUMP%" >nul 2>&1
echo   OK
echo.

echo ===========================================================
echo   Listo. La base de datos de esta compu quedo actualizada
echo   con los datos y la estructura actuales del servidor.
echo ===========================================================
echo.
echo  Guardar este archivo junto a los demas de esta carpeta -
echo  sirve para cualquier actualizacion futura, no solo para hoy.
echo  Cuando haga falta traer los cambios mas recientes del
echo  servidor, volver a correr este mismo archivo.
echo.
pause

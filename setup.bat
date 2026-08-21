@echo off
title Oga Pora - Instalacion
echo.
echo ===========================================================
echo        OGA PORA - Sistema de Gestion Comercial
echo                  Instalacion (Windows)
echo ===========================================================
echo.

echo [1/5] Verificando prerrequisitos...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   ERROR: Python no encontrado.
    echo   Descargar: https://www.python.org/downloads/
    echo   Marcar "Add Python to PATH" al instalar.
    pause & exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do echo   OK: %%i

node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   ERROR: Node.js no encontrado. Descargar: https://nodejs.org/
    pause & exit /b 1
)
for /f "tokens=*" %%i in ('node --version') do echo   OK: Node %%i

psql --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   ERROR: PostgreSQL no encontrado en el PATH.
    echo   Agregar al PATH: C:\Program Files\PostgreSQL\15\bin
    pause & exit /b 1
)
for /f "tokens=*" %%i in ('psql --version') do echo   OK: %%i
echo.

echo [2/5] Verificando archivo de configuracion (.env)...
if not exist "backend\.env" (
    echo   ERROR: Falta el archivo backend\.env
    echo   Crearlo segun la Guia de Instalacion, seccion 3.
    pause & exit /b 1
)
echo   OK: archivo .env encontrado.
echo.

echo [3/5] Configurando backend (Django)...
cd backend
python -m venv venv
call venv\Scripts\activate.bat
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo   Aplicando migraciones...
python manage.py migrate
echo   Creando categorias de gasto base...
python manage.py seed_categorias
echo   Recolectando archivos estaticos (admin de Django)...
rem Sin esto, con DEBUG=False el /admin/ responde 500: el storage de
rem WhiteNoise es de tipo Manifest y necesita staticfiles.json, que lo genera
rem este comando. Paso al que le faltaba: se descubrio el 21/08/2026 armando
rem la PC del Salon Comercial.
python manage.py collectstatic --noinput
echo.
echo   Ahora se creara el usuario administrador del sistema.
echo   Ingrese nombre de usuario y contrasena cuando se solicite:
python manage.py createsuperuser
call venv\Scripts\deactivate.bat
cd ..
echo   OK: Backend listo.
echo.

echo [4/5] Instalando dependencias del frontend...
cd frontend
call npm install --silent
cd ..
echo   OK: Frontend listo.
echo.

echo [5/5] Detectando IP de red local...
set LOCAL_IP=
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4" ^| findstr /v "127.0.0.1"') do (
    if not defined LOCAL_IP set LOCAL_IP=%%a
)
set LOCAL_IP=%LOCAL_IP: =%

echo.
echo ===========================================================
echo   Instalacion completada correctamente.
echo.
echo   Para iniciar el sistema:  iniciar.bat
echo.
echo   Acceso local:     http://localhost:5173
echo   Acceso red WiFi:  http://%LOCAL_IP%:5173
echo.
echo   Inicie sesion con el usuario administrador que acaba
echo   de crear, y desde la seccion Usuarios cree las demas
echo   cuentas (vendedores, cajeros, deposito).
echo ===========================================================
echo.
pause

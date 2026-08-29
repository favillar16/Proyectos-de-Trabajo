@echo off
title Oga Pora - Revision del codigo
cd /d "%~dp0"
echo.
echo ===========================================================
echo        OGA PORA - Revision automatica del codigo
echo ===========================================================
echo.
echo  Busca errores de programacion: nombres que no existen,
echo  codigo duplicado que se pisa, variables sin usar.
echo  Es para el tecnico, no para el uso diario del negocio.
echo.

if not exist "backend\venv\Scripts\activate.bat" (
    echo  ERROR: El sistema no esta instalado. Ejecutar primero: setup.bat
    pause
    exit /b 1
)

cd backend
call venv\Scripts\activate.bat

python -c "import ruff" 2>nul
if errorlevel 1 (
    echo  Instalando el revisor de codigo ^(solo la primera vez^)...
    pip install -q -r requirements-dev.txt
    echo.
)

python -m ruff check . --config ..\ruff.toml
set RESULTADO=%errorlevel%

echo.
echo  Revision de configuracion de Django...
python manage.py check --deploy

call venv\Scripts\deactivate.bat
cd ..

echo.
if %RESULTADO% equ 0 (
    echo   Sin errores de codigo.
) else (
    echo   Revisar los avisos de arriba.
)
echo.
pause

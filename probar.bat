@echo off
title Oga Pora - Pruebas automaticas
cd /d "%~dp0"
echo.
echo ===========================================================
echo        OGA PORA - Pruebas automaticas del sistema
echo ===========================================================
echo.
echo  Revisa que las cuentas del sistema sigan dando bien:
echo  stock, reservas, cobros, vuelto, permisos por rol.
echo.
echo  NO toca la base de datos del negocio: las pruebas usan
echo  una base temporal que se borra sola al terminar.
echo.

if not exist "backend\venv\Scripts\activate.bat" (
    echo  ERROR: El sistema no esta instalado. Ejecutar primero: setup.bat
    pause
    exit /b 1
)

cd backend
call venv\Scripts\activate.bat
python manage.py test --settings=config.settings_test
set RESULTADO=%errorlevel%
call venv\Scripts\deactivate.bat
cd ..

echo.
if %RESULTADO% equ 0 (
    echo ===========================================================
    echo   TODO BIEN. El sistema paso todas las pruebas.
    echo ===========================================================
) else (
    echo ===========================================================
    echo   ATENCION: alguna prueba fallo.
    echo.
    echo   Buscar arriba las lineas que empiezan con FAIL o ERROR:
    echo   ahi dice que prueba fallo y por que. Si no se entiende,
    echo   sacar una foto de la pantalla y pasarsela al tecnico.
    echo.
    echo   Mientras tanto, NO actualizar el sistema en la PC del
    echo   negocio.
    echo ===========================================================
)
echo.
pause

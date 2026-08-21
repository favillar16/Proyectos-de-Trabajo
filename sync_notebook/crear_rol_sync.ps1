# ============================================================================
#  Oga Pora - crea el rol de SOLO LECTURA que usa el sync de la notebook.
#
#  El sync de la notebook nunca debe entrar con el usuario de la aplicacion:
#  con esas credenciales podria escribir en la base del negocio, y la
#  notebook es un espejo de solo lectura. Este script crea "notebook_sync",
#  que puede leer todo y no puede modificar nada.
#
#  Ejecutar como Administrador (usar crear_rol_sync.bat).
#  Es idempotente: si el rol ya existe, le actualiza la contrasena.
#
#  La contrasena se genera sola y queda guardada en
#  sync_notebook\credenciales_sync.txt (ignorado por git) para poder pegarla
#  en el config.env de la notebook.
# ============================================================================

param(
    [string] $Password = '',
    [string] $Rol      = 'notebook_sync',
    [string] $Base     = 'ceramica_db'
)

$ErrorActionPreference = 'Stop'

function Ok  ($m) { Write-Host "[OK]  $m" -ForegroundColor Green }
function Info($m) { Write-Host "[..]  $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "[!]   $m" -ForegroundColor Yellow }
function Bad ($m) { Write-Host "[X]   $m" -ForegroundColor Red }

$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

$pgDir   = 'C:\Program Files\PostgreSQL\15'
$psql    = Join-Path $pgDir 'bin\psql.exe'
$hba     = Join-Path $pgDir 'data\pg_hba.conf'
$carpeta = Split-Path -Parent $MyInvocation.MyCommand.Path
$archivoCred = Join-Path $carpeta 'credenciales_sync.txt'

if (-not (Test-Path $psql)) {
    Bad "No se encontro psql en $psql"
    Read-Host "Enter para salir"
    exit 1
}

# --- Contrasena: alfanumerica a proposito ----------------------------------
# Sin simbolos para que se pueda pegar sin problemas en config.env, en psql
# y en la linea de comandos de Windows sin comillas ni escapes.
if (-not $Password) {
    $abc = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
    $rnd = New-Object System.Random
    $Password = -join (1..24 | ForEach-Object { $abc[$rnd.Next(0, $abc.Length)] })
}

Write-Host ""
Write-Host "=== Rol de solo lectura para el sync de la notebook ===" -ForegroundColor White
Write-Host ""
Write-Host "  Rol         : $Rol"
Write-Host "  Base        : $Base"
Write-Host "  Contrasena  : $Password" -ForegroundColor Yellow
Write-Host ""

$sql = @"
DO
`$`$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$Rol') THEN
        ALTER ROLE $Rol WITH LOGIN PASSWORD '$Password';
        RAISE NOTICE 'El rol $Rol ya existia: se actualizo la contrasena.';
    ELSE
        CREATE ROLE $Rol WITH LOGIN PASSWORD '$Password';
        RAISE NOTICE 'Rol $Rol creado.';
    END IF;
END
`$`$;
GRANT CONNECT ON DATABASE $Base TO $Rol;
GRANT pg_read_all_data TO $Rol;
"@

$archivoSql = Join-Path $env:TEMP ('crear_rol_sync_{0}.sql' -f (Get-Date -Format 'HHmmss'))
Set-Content -Path $archivoSql -Value $sql -Encoding UTF8

# --- Como nos autenticamos como postgres -----------------------------------
Write-Host "Para crear el rol hay que entrar a PostgreSQL como el superusuario"
Write-Host "'postgres'. Hay dos formas:"
Write-Host ""
Write-Host "  1) Tengo la contrasena de 'postgres'  (lo normal)"
Write-Host "  2) No la tengo / no la recuerdo       (habilita el acceso local sin"
Write-Host "     contrasena unos segundos, crea el rol y lo deja como estaba)"
Write-Host ""
$opcion = Read-Host "Opcion [1/2]"

$ok = $false

if ($opcion -eq '2') {
    if (-not $esAdmin) {
        Bad "La opcion 2 necesita Administrador. Cerrar y usar crear_rol_sync.bat."
        Read-Host "Enter para salir"
        exit 1
    }

    # Se antepone una linea 'trust' para 127.0.0.1: pg_hba aplica la PRIMERA
    # regla que coincide, asi que esta gana sobre la scram-sha-256 de mas
    # abajo. Solo afecta a conexiones locales de esta misma PC y se revierte
    # en el finally, pase lo que pase.
    Info "Habilitando acceso local temporal (se revierte al terminar)"
    $respaldoHba = "$hba.bak_$(Get-Date -Format yyyyMMdd_HHmmss)"
    Copy-Item $hba $respaldoHba
    $original = Get-Content $hba -Raw

    try {
        $marca = "# --- Oga Pora: acceso temporal para crear el rol de sync (se borra solo) ---"
        Set-Content -Path $hba -Value ("$marca`r`nhost    all             postgres        127.0.0.1/32            trust`r`n`r`n" + $original)
        Restart-Service postgresql-x64-15
        Start-Sleep -Seconds 3

        & $psql --host=127.0.0.1 --username=postgres --dbname=$Base --set=ON_ERROR_STOP=1 --file=$archivoSql
        if ($LASTEXITCODE -eq 0) { $ok = $true }
    }
    finally {
        Set-Content -Path $hba -Value $original -NoNewline
        Restart-Service postgresql-x64-15
        Start-Sleep -Seconds 3
        Ok "pg_hba.conf restaurado (copia de seguridad: $respaldoHba)"
    }
}
else {
    Info "psql va a pedir la contrasena del usuario 'postgres'"
    & $psql --host=127.0.0.1 --username=postgres --dbname=$Base --set=ON_ERROR_STOP=1 --file=$archivoSql
    if ($LASTEXITCODE -eq 0) { $ok = $true }
}

Remove-Item $archivoSql -ErrorAction SilentlyContinue

if (-not $ok) {
    Bad "No se pudo crear el rol (codigo $LASTEXITCODE)."
    Bad "Si fue por la contrasena de 'postgres', volver a correr y elegir la opcion 2."
    Read-Host "Enter para salir"
    exit 1
}

# --- Verificacion: que pueda leer y que NO pueda escribir ------------------
Info "Verificando el rol recien creado"
$env:PGPASSWORD = $Password

$cant = & $psql --host=127.0.0.1 --username=$Rol --dbname=$Base --tuples-only --no-align --command="SELECT count(*) FROM productos;" 2>&1
if ($LASTEXITCODE -eq 0) {
    Ok "$Rol puede leer la base ($($cant.ToString().Trim()) productos)"
} else {
    Bad "El rol no pudo conectarse: $cant"
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    Read-Host "Enter para salir"
    exit 1
}

$prev = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& $psql --host=127.0.0.1 --username=$Rol --dbname=$Base --quiet --set=ON_ERROR_STOP=1 `
        --command="CREATE TABLE prueba_solo_lectura (x int);" *> $null
$ErrorActionPreference = $prev
if ($LASTEXITCODE -ne 0) {
    Ok "$Rol NO puede escribir (es lo que corresponde)"
} else {
    Warn "ATENCION: el rol pudo crear una tabla. Revisar permisos a mano."
    & $psql --host=127.0.0.1 --username=$Rol --dbname=$Base --quiet --command="DROP TABLE IF EXISTS prueba_solo_lectura;" *> $null
}
Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue

# --- Dejar la contrasena a mano para pegarla en la notebook ----------------
$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '192.168.*' } | Select-Object -First 1).IPAddress
$texto = @"
Oga Pora - credenciales del sync de la notebook
Generado: $(Get-Date -Format 'dd/MM/yyyy HH:mm')

Rol de solo lectura en la PC servidor ($env:COMPUTERNAME):
  usuario     : $Rol
  contrasena  : $Password

Pegar en sync_notebook\config.env DE LA NOTEBOOK:

SERVIDOR_HOST=$ip
SERVIDOR_DB_PUERTO=5432
SERVIDOR_DB_NOMBRE=$Base
SERVIDOR_DB_USUARIO=$Rol
SERVIDOR_DB_PASSWORD=$Password
SERVIDOR_MEDIA_URL=
SERVIDOR_MEDIA_UNC=

(LOCAL_DB_* se completan con los datos del PostgreSQL de la notebook.)

Este archivo esta ignorado por git a proposito: no se sube al repositorio.
"@
Set-Content -Path $archivoCred -Value $texto -Encoding UTF8

Write-Host ""
Write-Host "=== Listo ===" -ForegroundColor White
Write-Host $texto
Write-Host "Guardado en: $archivoCred" -ForegroundColor DarkGray
Write-Host ""
Read-Host "Enter para cerrar"

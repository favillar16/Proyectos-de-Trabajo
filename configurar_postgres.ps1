# ============================================================================
#  Oga Pora - deja PostgreSQL listo en la PC servidor:
#    1. le pone contrasena conocida al superusuario "postgres"
#    2. crea el rol de SOLO LECTURA "notebook_sync" que usa el sync
#
#  Las dos contrasenas salen de credenciales_servidor.txt (raiz del proyecto),
#  que esta ignorado por git a proposito: no viajan nunca al repositorio.
#
#  Ejecutar como Administrador (usar configurar_postgres.bat).
#  Es idempotente: se puede volver a correr sin romper nada.
#
#  Como entra sin saber la contrasena actual de "postgres": antepone una linea
#  "trust" para 127.0.0.1 en pg_hba.conf, reinicia el servicio, hace los
#  cambios y restaura el archivo original en un finally, pase lo que pase. Es
#  el procedimiento estandar de recuperacion de PostgreSQL. Solo afecta a
#  conexiones desde esta misma PC y dura unos segundos; las reglas de la red
#  del local no se tocan.
# ============================================================================

$ErrorActionPreference = 'Stop'

function Ok  ($m) { Write-Host "[OK]  $m" -ForegroundColor Green }
function Info($m) { Write-Host "[..]  $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "[!]   $m" -ForegroundColor Yellow }
function Bad ($m) { Write-Host "[X]   $m" -ForegroundColor Red }

function Salir($codigo) {
    Write-Host ""
    Read-Host "Enter para cerrar"
    exit $codigo
}

$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $esAdmin) {
    Bad "Este script necesita permisos de Administrador."
    Bad "Cerrar esta ventana y usar configurar_postgres.bat (doble clic)."
    Salir 1
}

$raiz     = Split-Path -Parent $MyInvocation.MyCommand.Path
$archivo  = Join-Path $raiz 'credenciales_servidor.txt'
$pgDir    = 'C:\Program Files\PostgreSQL\15'
$psql     = Join-Path $pgDir 'bin\psql.exe'
$hba      = Join-Path $pgDir 'data\pg_hba.conf'
$servicio = 'postgresql-x64-15'
$base     = 'ceramica_db'
$rol      = 'notebook_sync'

Write-Host ""
Write-Host "=== Oga Pora - configuracion de PostgreSQL ===" -ForegroundColor White
Write-Host ""

foreach ($ruta in @($archivo, $psql, $hba)) {
    if (-not (Test-Path $ruta)) {
        Bad "No se encontro: $ruta"
        Salir 1
    }
}

# --- Leer las contrasenas del archivo de credenciales ----------------------
$cfg = @{}
Get-Content $archivo | ForEach-Object {
    $l = $_.Trim()
    if ($l -and -not $l.StartsWith('#') -and $l.Contains('=')) {
        $k, $v = $l.Split('=', 2)
        $cfg[$k.Trim()] = $v.Trim()
    }
}

$clavePg  = $cfg['POSTGRES_PASSWORD']
$claveRol = $cfg['NOTEBOOK_SYNC_PASSWORD']

if (-not $clavePg -or -not $claveRol) {
    Bad "Faltan POSTGRES_PASSWORD y/o NOTEBOOK_SYNC_PASSWORD en:"
    Bad "  $archivo"
    Salir 1
}
Ok "Credenciales leidas de credenciales_servidor.txt"

# --- SQL a aplicar ---------------------------------------------------------
$sql = @"
ALTER ROLE postgres WITH PASSWORD '$clavePg';

DO
`$`$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$rol') THEN
        ALTER ROLE $rol WITH LOGIN PASSWORD '$claveRol';
        RAISE NOTICE 'El rol $rol ya existia: se actualizo la contrasena.';
    ELSE
        CREATE ROLE $rol WITH LOGIN PASSWORD '$claveRol';
        RAISE NOTICE 'Rol $rol creado.';
    END IF;
END
`$`$;

GRANT CONNECT ON DATABASE $base TO $rol;
GRANT pg_read_all_data TO $rol;
"@

$archivoSql = Join-Path $env:TEMP ('ogapora_pg_{0}.sql' -f (Get-Date -Format 'HHmmss'))
Set-Content -Path $archivoSql -Value $sql -Encoding UTF8

# --- Ventana de acceso local sin contrasena --------------------------------
Info "Habilitando acceso local temporal (se revierte al terminar)"
$respaldo = "$hba.bak_$(Get-Date -Format yyyyMMdd_HHmmss)"
Copy-Item $hba $respaldo
$original = Get-Content $hba -Raw
$aplicado = $false

try {
    # pg_hba aplica la PRIMERA regla que coincide, por eso va arriba de todo.
    $marca = "# --- Oga Pora: acceso temporal para configurar PostgreSQL (se revierte solo) ---"
    $linea = "host    all             postgres        127.0.0.1/32            trust"
    Set-Content -Path $hba -Value ("$marca`r`n$linea`r`n`r`n" + $original)

    Restart-Service $servicio
    Start-Sleep -Seconds 4
    Ok "PostgreSQL reiniciado con el acceso temporal"

    $previo = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $psql --host=127.0.0.1 --username=postgres --dbname=$base --set=ON_ERROR_STOP=1 --file=$archivoSql
    $codigo = $LASTEXITCODE
    $ErrorActionPreference = $previo

    if ($codigo -eq 0) {
        $aplicado = $true
        Ok "Contrasena de 'postgres' actualizada y rol '$rol' listo"
    } else {
        Bad "psql fallo (codigo $codigo)"
    }
}
finally {
    Remove-Item $archivoSql -ErrorAction SilentlyContinue
    Set-Content -Path $hba -Value $original -NoNewline
    Restart-Service $servicio
    Start-Sleep -Seconds 4
    Ok "pg_hba.conf restaurado (copia: $(Split-Path -Leaf $respaldo))"
}

if (-not $aplicado) { Salir 1 }

# --- Verificacion ----------------------------------------------------------
Info "Verificando"
$previo = $ErrorActionPreference
$ErrorActionPreference = 'Continue'

$env:PGPASSWORD = $clavePg
$v = & $psql --host=127.0.0.1 --username=postgres --dbname=$base --tuples-only --no-align --command="SELECT 'ok';" 2>&1
if ($LASTEXITCODE -eq 0) { Ok "'postgres' entra con la contrasena nueva" }
else { Bad "'postgres' NO pudo entrar: $v" }

$env:PGPASSWORD = $claveRol
$cant = & $psql --host=127.0.0.1 --username=$rol --dbname=$base --tuples-only --no-align --command="SELECT count(*) FROM productos;" 2>&1
if ($LASTEXITCODE -eq 0) { Ok "'$rol' puede leer la base ($($cant.ToString().Trim()) productos)" }
else { Bad "'$rol' NO pudo conectarse: $cant" }

& $psql --host=127.0.0.1 --username=$rol --dbname=$base --set=ON_ERROR_STOP=1 `
        --command="CREATE TABLE prueba_solo_lectura (x int);" *> $null
if ($LASTEXITCODE -ne 0) {
    Ok "'$rol' NO puede escribir (es lo que corresponde)"
} else {
    Warn "ATENCION: el rol pudo crear una tabla. Revisar los permisos a mano."
    & $psql --host=127.0.0.1 --username=$rol --dbname=$base --command="DROP TABLE IF EXISTS prueba_solo_lectura;" *> $null
}

Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
$ErrorActionPreference = $previo

# --- Resumen ---------------------------------------------------------------
Write-Host ""
Write-Host "=== Listo ===" -ForegroundColor White
Write-Host "  Superusuario 'postgres' : contrasena de credenciales_servidor.txt"
Write-Host "  Rol de solo lectura     : $rol"
Write-Host ""
Write-Host "  Las dos contrasenas estan en:" -ForegroundColor DarkGray
Write-Host "  $archivo" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  En la notebook: pegar el bloque de ese archivo en"
Write-Host "  sync_notebook\config.env y completar los LOCAL_DB_*."
Salir 0

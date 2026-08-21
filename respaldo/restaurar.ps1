# Restaura un respaldo creado por respaldo.ps1 en ESTA computadora.
#
# Uso:
#   restaurar.bat                                  -> usa el respaldo más nuevo de <repo>\respaldos\
#   restaurar.bat D:\respaldo_20260820_143000      -> usa uno puntual
#
# ⚠️ DESTRUCTIVO: borra y recrea por completo la base de datos de esta PC.
# Pensado para dos escenarios:
#   a) Migrar el sistema a la PC servidor definitiva (caso principal).
#   b) Recuperar la PC servidor después de una rotura.
#
# NO usar esto para "pasarle los datos" a la PC de caja o de depósito: esas
# son clientes, no tienen base propia y no deben tenerla (ver
# docs/pc_caja.md — dos bases = dos stocks distintos = sobreventa).

param(
    [string]$Origen = '',
    [switch]$SinConfirmar
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_comun.ps1"

$repoRaiz = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "===========================================================" -ForegroundColor White
Write-Host "   OGA PORA - Restaurar respaldo" -ForegroundColor White
Write-Host "===========================================================" -ForegroundColor White

try {
    # ─── Elegir el respaldo ──────────────────────────────────────────────────
    if (-not $Origen) {
        $carpetaRespaldos = Join-Path $repoRaiz 'respaldos'
        if (-not (Test-Path $carpetaRespaldos)) {
            throw "No se indicó ningún respaldo y no existe la carpeta $carpetaRespaldos. Uso: restaurar.bat <carpeta_del_respaldo>"
        }
        $masNuevo = Get-ChildItem $carpetaRespaldos -Directory -Filter 'respaldo_*' |
                    Sort-Object Name -Descending | Select-Object -First 1
        if (-not $masNuevo) {
            throw "No hay respaldos en $carpetaRespaldos. Uso: restaurar.bat <carpeta_del_respaldo>"
        }
        $Origen = $masNuevo.FullName
    }

    $archivoSql = Join-Path $Origen 'base_datos.sql'
    if (-not (Test-Path $archivoSql)) {
        throw "La carpeta $Origen no parece un respaldo válido: falta base_datos.sql"
    }

    # ─── Mostrar qué se va a restaurar y sobre qué ───────────────────────────
    $cfg = Leer-EnvBackend -RepoRaiz $repoRaiz
    $pg  = Resolver-BinariosPg

    $dbNombre   = Valor-O-Default $cfg 'DB_NAME'     'ceramica_db'
    $dbUsuario  = Valor-O-Default $cfg 'DB_USER'     'ceramica_user'
    $dbPassword = Valor-O-Default $cfg 'DB_PASSWORD' ''
    $dbPuerto   = Valor-O-Default $cfg 'DB_PORT'     '5432'

    $infoPath = Join-Path $Origen 'info.json'
    Write-Host ""
    Write-Host "  Respaldo a restaurar:"
    Write-Host "    $Origen"
    if (Test-Path $infoPath) {
        $info = Get-Content $infoPath -Raw | ConvertFrom-Json
        Write-Host "    Fecha  : $($info.fecha)"
        Write-Host "    Equipo : $($info.equipo_origen)"
        Write-Host "    Fotos  : $($info.fotos_cantidad)"
    }
    Write-Host ""
    Write-Host "  Se va a restaurar sobre ESTA PC ($env:COMPUTERNAME):"
    Write-Host "    Base de datos: $dbNombre (puerto $dbPuerto)"

    # ─── Confirmación explícita ──────────────────────────────────────────────
    if (-not $SinConfirmar) {
        Write-Host ""
        Write-Host "  ATENCION: la base '$dbNombre' de esta PC se borra por completo" -ForegroundColor Yellow
        Write-Host "  y se reemplaza por la del respaldo. Lo que haya ahora se pierde." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  Antes de seguir, cerrar el sistema en esta PC (las dos"    -ForegroundColor Yellow
        Write-Host "  ventanas negras que abre iniciar.bat)."                     -ForegroundColor Yellow
        Write-Host ""
        $rta = Read-Host "  Escribir SI (en mayusculas) para continuar"
        if ($rta -cne 'SI') {
            Write-Host ""
            Write-Host "  Cancelado, no se tocó nada." -ForegroundColor Yellow
            Write-Host ""
            exit 0
        }
    }

    # ─── 1) Recrear la base desde cero ───────────────────────────────────────
    # Se recrea en vez de restaurar encima por el mismo motivo que el sync de
    # la notebook (ver sync_notebook.ps1): si la base actual tiene tablas de
    # una versión distinta, el restore se corta a la mitad por dependencias
    # de foreign key y deja la base a medio armar.
    Escribir-Paso "[1/3] Recreando la base de datos..."

    $env:PGPASSWORD = $dbPassword
    $logRecreate = Join-Path $env:TEMP 'ogapora_recreate.log'

    & $pg.Psql `
        --host=localhost --port=$dbPuerto --username=$dbUsuario `
        --dbname=postgres --set=ON_ERROR_STOP=1 --quiet `
        --command="DROP DATABASE IF EXISTS $dbNombre WITH (FORCE);" `
        --command="CREATE DATABASE $dbNombre OWNER $dbUsuario;" `
        *> $logRecreate

    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo recrear la base (código $LASTEXITCODE). Ver $logRecreate. Causa habitual: el usuario '$dbUsuario' no tiene permiso CREATEDB — corregir con:  ALTER ROLE $dbUsuario CREATEDB;  desde psql como postgres."
    }
    Escribir-Ok "base '$dbNombre' recreada vacía"

    # ─── 2) Cargar los datos ─────────────────────────────────────────────────
    Escribir-Paso "[2/3] Cargando los datos (puede tardar)..."

    $logRestore = Join-Path $env:TEMP 'ogapora_restore.log'
    & $pg.Psql `
        --host=localhost --port=$dbPuerto --username=$dbUsuario `
        --dbname=$dbNombre --set=ON_ERROR_STOP=1 --quiet `
        --file=$archivoSql `
        *> $logRestore

    if ($LASTEXITCODE -ne 0) {
        throw "La restauración falló (código $LASTEXITCODE). Ver $logRestore"
    }
    Escribir-Ok "datos cargados"

    # ─── 3) Fotos de productos ───────────────────────────────────────────────
    Escribir-Paso "[3/3] Copiando las fotos de productos..."

    $mediaOrigen  = Join-Path $Origen 'media'
    $mediaDestino = Join-Path $repoRaiz 'backend\media'

    if (Test-Path $mediaOrigen) {
        # /E y no /MIR a propósito: agrega y pisa, pero no borra lo que ya
        # esté en esta PC. Una foto de más es un archivo que nadie referencia
        # (inofensivo); una foto de menos es un producto con la imagen rota.
        & robocopy $mediaOrigen $mediaDestino /E /NFL /NDL /NJH /NJS /R:2 /W:2 | Out-Null
        if ($LASTEXITCODE -ge 8) {
            throw "robocopy falló al copiar las fotos (código $LASTEXITCODE)."
        }
        $global:LASTEXITCODE = 0

        $cant = (Get-ChildItem $mediaDestino -Recurse -File -ErrorAction SilentlyContinue).Count
        Escribir-Ok "fotos restauradas ($cant archivos en backend\media)"
    }
    else {
        Write-Host "  AVISO: el respaldo no trae carpeta media — los productos van a quedar sin fotos." -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "===========================================================" -ForegroundColor Green
    Write-Host "   Restauracion completa" -ForegroundColor Green
    Write-Host ""
    Write-Host "   Siguiente paso: correr  iniciar.bat  y entrar al sistema"
    Write-Host "   para verificar que estan los productos y sus fotos."
    Write-Host ""
    Write-Host "   Los usuarios y contrasenas son los del equipo de origen,"
    Write-Host "   no los de esta PC."
    Write-Host "===========================================================" -ForegroundColor Green
    Write-Host ""
    exit 0
}
catch {
    Escribir-Error-Fatal $_.Exception.Message
    exit 1
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}

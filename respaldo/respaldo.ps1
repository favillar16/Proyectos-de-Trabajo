# Crea un respaldo completo del sistema: base de datos + fotos de productos.
#
# Por qué las dos cosas juntas: ImagenProducto/ImagenVariante guardan en la
# base solo la RUTA del archivo (settings.MEDIA_ROOT = backend/media). Un dump
# de la base sin las fotos restaura un catálogo entero con todas las imágenes
# rotas, y una carpeta de fotos sin la base son archivos sueltos que nadie
# referencia. Siempre viajan juntos.
#
# Uso:
#   respaldo.bat                      -> guarda en <repo>\respaldos\
#   respaldo.bat D:\                  -> guarda en un pendrive
#
# No hace falta frenar el sistema: pg_dump toma una foto consistente de la
# base aunque haya gente vendiendo en ese momento.

param(
    [string]$Destino = ''
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_comun.ps1"

$repoRaiz = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "===========================================================" -ForegroundColor White
Write-Host "   OGA PORA - Respaldo del sistema" -ForegroundColor White
Write-Host "===========================================================" -ForegroundColor White

try {
    # ─── Preparación ─────────────────────────────────────────────────────────
    $cfg = Leer-EnvBackend -RepoRaiz $repoRaiz
    $pg  = Resolver-BinariosPg

    $dbNombre   = Valor-O-Default $cfg 'DB_NAME'     'ceramica_db'
    $dbUsuario  = Valor-O-Default $cfg 'DB_USER'     'ceramica_user'
    $dbPassword = Valor-O-Default $cfg 'DB_PASSWORD' ''
    $dbHost     = Valor-O-Default $cfg 'DB_HOST'     'localhost'
    $dbPuerto   = Valor-O-Default $cfg 'DB_PORT'     '5432'

    if (-not $Destino) { $Destino = Join-Path $repoRaiz 'respaldos' }
    if (-not (Test-Path $Destino)) {
        New-Item -ItemType Directory -Path $Destino -Force | Out-Null
    }

    $sello   = Get-Date -Format 'yyyyMMdd_HHmmss'
    $carpeta = Join-Path $Destino "respaldo_$sello"
    New-Item -ItemType Directory -Path $carpeta -Force | Out-Null

    Write-Host ""
    Write-Host "  Base de datos : $dbNombre en ${dbHost}:${dbPuerto}"
    Write-Host "  Destino       : $carpeta"

    # ─── 1) Base de datos ────────────────────────────────────────────────────
    Escribir-Paso "[1/3] Copiando la base de datos..."

    $archivoSql = Join-Path $carpeta 'base_datos.sql'
    $env:PGPASSWORD = $dbPassword

    # Mismos flags que usa el sync de la notebook: el dump se puede restaurar
    # en una PC donde los roles de Postgres tengan otros nombres.
    & $pg.PgDump `
        --host=$dbHost `
        --port=$dbPuerto `
        --username=$dbUsuario `
        --dbname=$dbNombre `
        --clean --if-exists --no-owner --no-privileges `
        --file=$archivoSql

    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $archivoSql) -or (Get-Item $archivoSql).Length -eq 0) {
        throw "pg_dump falló (código $LASTEXITCODE) o generó un archivo vacío. Revisar que PostgreSQL esté corriendo y que las credenciales de backend\.env sean correctas."
    }

    $tamSql = (Get-Item $archivoSql).Length
    Escribir-Ok "base de datos copiada ($(Formatear-Tamano $tamSql))"

    # ─── 2) Fotos de productos ───────────────────────────────────────────────
    Escribir-Paso "[2/3] Copiando las fotos de productos..."

    $mediaOrigen  = Join-Path $repoRaiz 'backend\media'
    $mediaDestino = Join-Path $carpeta 'media'
    $tamMedia     = 0
    $archivosMedia = 0

    if (Test-Path $mediaOrigen) {
        # /E incluye subcarpetas (también vacías); /NFL /NDL /NJH /NJS dejan
        # la salida corta — con miles de fotos, el detalle no aporta nada.
        & robocopy $mediaOrigen $mediaDestino /E /NFL /NDL /NJH /NJS /R:2 /W:2 | Out-Null

        # robocopy usa códigos 0-7 para "todo bien" (0 = sin cambios, 1 =
        # archivos copiados, etc.). Recién 8 o más es un error real.
        if ($LASTEXITCODE -ge 8) {
            throw "robocopy falló al copiar las fotos (código $LASTEXITCODE)."
        }
        $global:LASTEXITCODE = 0

        $tamMedia      = Tamano-Carpeta $mediaDestino
        $archivosMedia = (Get-ChildItem $mediaDestino -Recurse -File -ErrorAction SilentlyContinue).Count
        Escribir-Ok "$archivosMedia fotos copiadas ($(Formatear-Tamano $tamMedia))"
    }
    else {
        Write-Host "  AVISO: no existe backend\media — no hay fotos que respaldar." -ForegroundColor Yellow
    }

    # ─── 3) Ficha del respaldo ───────────────────────────────────────────────
    # Sirve para saber, meses después, de qué equipo y de qué versión del
    # sistema salió este respaldo antes de restaurarlo en algún lado.
    Escribir-Paso "[3/3] Escribiendo la ficha del respaldo..."

    $commit = ''
    try {
        Push-Location $repoRaiz
        $commit = (& git rev-parse --short HEAD 2>$null)
        Pop-Location
    } catch { $commit = '' }

    $info = [ordered]@{
        fecha              = (Get-Date).ToString('o')
        equipo_origen      = $env:COMPUTERNAME
        base_datos         = $dbNombre
        archivo_sql        = 'base_datos.sql'
        tamano_sql_bytes   = $tamSql
        fotos_cantidad     = $archivosMedia
        tamano_media_bytes = $tamMedia
        commit             = $commit
    }
    $info | ConvertTo-Json | Set-Content -Path (Join-Path $carpeta 'info.json') -Encoding utf8
    Escribir-Ok "ficha escrita (info.json)"

    # ─── Resumen ─────────────────────────────────────────────────────────────
    $total = Tamano-Carpeta $carpeta
    Write-Host ""
    Write-Host "===========================================================" -ForegroundColor Green
    Write-Host "   Respaldo completo - $(Formatear-Tamano $total)" -ForegroundColor Green
    Write-Host ""
    Write-Host "   $carpeta"
    Write-Host ""
    Write-Host "   Para restaurarlo en otra PC: copiar esa carpeta entera"
    Write-Host "   a la PC nueva y correr ahi  respaldo\restaurar.bat"
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

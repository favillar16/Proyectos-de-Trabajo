# Trae las fotos de productos desde el repositorio de git. Es el otro lado de
# subir_fotos.bat: se corre en la PC servidor.
#
# No hace falta si el proyecto se clono con "git clone": el clone ya trae las
# fotos. Sirve para (a) un proyecto que se copio de otra forma, y (b) volver a
# traer las fotos nuevas que se hayan cargado despues en el equipo de armado.
#
# Uso:
#   traer_fotos.bat

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_comun.ps1"

$repoRaiz   = Split-Path -Parent $PSScriptRoot
$rutaMedia  = Join-Path $repoRaiz 'backend\media'
$manifiesto = Join-Path $PSScriptRoot 'fotos_manifiesto.json'

Write-Host ""
Write-Host "===========================================================" -ForegroundColor White
Write-Host "   OGA PORA - Traer fotos desde el repositorio" -ForegroundColor White
Write-Host "===========================================================" -ForegroundColor White

try {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "No se encontro git. Instalar Git para Windows y volver a intentar."
    }

    & git -C $repoRaiz rev-parse --is-inside-work-tree 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "$repoRaiz no es un repositorio de git. Si el proyecto se copio a mano, clonarlo de nuevo con: git clone <url del repo>"
    }

    # --- 1) Bajar -------------------------------------------------------------
    Escribir-Paso "[1/2] Bajando los cambios del repositorio..."

    & git -C $repoRaiz pull
    if ($LASTEXITCODE -ne 0) {
        throw "git pull fallo (codigo $LASTEXITCODE). Si se queja de cambios locales sin guardar, esta PC tiene modificaciones propias: resolverlas antes (git status)."
    }
    Escribir-Ok "repositorio actualizado"

    # --- 2) Verificar ---------------------------------------------------------
    # Que el pull haya terminado bien no significa que estan TODAS las fotos:
    # pudieron haberse subido a medias. Por eso se compara contra el manifiesto
    # que escribio el equipo de origen.
    Escribir-Paso "[2/2] Verificando las fotos..."

    if (-not (Test-Path $rutaMedia)) {
        throw "No existe $rutaMedia despues del pull. El equipo de origen todavia no corrio subir_fotos.bat."
    }

    $archivos = @(Get-ChildItem $rutaMedia -Recurse -File -ErrorAction SilentlyContinue)
    $bytes    = Tamano-Carpeta $rutaMedia

    Write-Host "  En esta PC : $($archivos.Count) fotos ($(Formatear-Tamano $bytes))"

    if (Test-Path $manifiesto) {
        $m = Get-Content $manifiesto -Raw | ConvertFrom-Json
        Write-Host "  Manifiesto : $($m.fotos_cantidad) fotos ($(Formatear-Tamano ([long]$m.fotos_bytes)))"
        Write-Host "  Subidas el : $($m.fecha) desde $($m.equipo_origen)"

        if ($archivos.Count -lt $m.fotos_cantidad) {
            throw "Faltan $($m.fotos_cantidad - $archivos.Count) fotos. Volver a correr subir_fotos.bat en el equipo de origen y despues este script de nuevo."
        }
        Escribir-Ok "estan las $($m.fotos_cantidad) fotos del equipo de origen"
    }
    else {
        Write-Host "  (sin manifiesto: el equipo de origen todavia no corrio subir_fotos.bat)" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "  -------------------------------------------------------" -ForegroundColor White
    Write-Host "  Las fotos ya estan. FALTA LA BASE DE DATOS:" -ForegroundColor Yellow
    Write-Host "  sin ella estos archivos son fotos sueltas que nadie" -ForegroundColor Yellow
    Write-Host "  referencia, y el sistema arranca con el catalogo vacio." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Traer base_datos.sql del equipo de armado (correo, Drive," -ForegroundColor White
    Write-Host "  WhatsApp Web: son ~333 KB) y despues:" -ForegroundColor White
    Write-Host ""
    Write-Host "      respaldo\restaurar.bat <carpeta del respaldo>"
    Write-Host ""
    Write-Host "  Detalle en docs/respaldo_y_migracion.md seccion 3.5." -ForegroundColor White
    Write-Host "  -------------------------------------------------------" -ForegroundColor White
    Write-Host ""
}
catch {
    Escribir-Error-Fatal $_.Exception.Message
    exit 1
}

# Sube las fotos de productos (backend\media) al repositorio de git, para
# trasladarlas a otra PC cuando no hay pendrive a mano.
#
# Por que esto sirve para las fotos y NO para la base de datos: el repositorio
# del proyecto es PUBLICO. Las fotos son el catalogo y se pueden publicar sin
# problema. Un dump de la base no: lleva clientes, ventas, precios y los hashes
# de contrasena de los usuarios. Ademas la base son ~333 KB y viaja por
# cualquier otro medio; las fotos son ~35 MB y son las que de verdad necesitan
# un transporte. Ver docs/respaldo_y_migracion.md seccion 3.5.
#
# Uso:
#   subir_fotos.bat
#
# Solo toca backend\media y el manifiesto: cualquier otro cambio que haya en el
# arbol de trabajo queda como estaba, sin agregar ni commitear.

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_comun.ps1"

$repoRaiz   = Split-Path -Parent $PSScriptRoot
$rutaMedia  = Join-Path $repoRaiz 'backend\media'
$manifiesto = Join-Path $PSScriptRoot 'fotos_manifiesto.json'

Write-Host ""
Write-Host "===========================================================" -ForegroundColor White
Write-Host "   OGA PORA - Subir fotos al repositorio" -ForegroundColor White
Write-Host "===========================================================" -ForegroundColor White

try {
    # --- Comprobaciones previas ---------------------------------------------
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "No se encontro git. Instalar Git para Windows y volver a intentar."
    }
    if (-not (Test-Path $rutaMedia)) {
        throw "No existe $rutaMedia. Este script se corre en el equipo que TIENE las fotos."
    }

    $rama = (& git -C $repoRaiz rev-parse --abbrev-ref HEAD 2>$null)
    if ($LASTEXITCODE -ne 0) { throw "$repoRaiz no es un repositorio de git." }

    # --- 1) Inventario de lo que hay ----------------------------------------
    Escribir-Paso "[1/4] Revisando las fotos..."

    $archivos = @(Get-ChildItem $rutaMedia -Recurse -File -ErrorAction SilentlyContinue)
    if ($archivos.Count -eq 0) {
        throw "La carpeta $rutaMedia esta vacia. No hay nada para subir."
    }

    $bytes = Tamano-Carpeta $rutaMedia
    Write-Host "  Fotos : $($archivos.Count) archivos ($(Formatear-Tamano $bytes))"
    Write-Host "  Rama  : $rama"

    # GitHub rechaza archivos de mas de 100 MB. Avisar antes de armar el commit,
    # no despues de que falle el push.
    $pesados = @($archivos | Where-Object { $_.Length -gt 90MB })
    if ($pesados.Count -gt 0) {
        throw "Hay $($pesados.Count) archivo(s) de mas de 90 MB (GitHub rechaza los de 100 MB). El primero: $($pesados[0].FullName)"
    }

    # --- 2) Manifiesto -------------------------------------------------------
    # Sirve para que la PC servidor verifique que le llegaron TODAS las fotos,
    # sin tener que contarlas a mano contra el equipo de origen.
    Escribir-Paso "[2/4] Escribiendo el manifiesto..."

    [ordered]@{
        fecha          = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
        equipo_origen  = $env:COMPUTERNAME
        fotos_cantidad = $archivos.Count
        fotos_bytes    = $bytes
        rama           = $rama
    } | ConvertTo-Json | Set-Content -Path $manifiesto -Encoding UTF8

    Escribir-Ok "manifiesto actualizado ($($archivos.Count) fotos)"

    # --- 3) Commit -----------------------------------------------------------
    Escribir-Paso "[3/4] Agregando las fotos al repositorio..."

    & git -C $repoRaiz add -- 'backend/media' 'respaldo/fotos_manifiesto.json'
    if ($LASTEXITCODE -ne 0) { throw "git add fallo (codigo $LASTEXITCODE)." }

    $pendiente = @(& git -C $repoRaiz diff --cached --name-only)
    if ($pendiente.Count -eq 0) {
        Escribir-Ok "no hay fotos nuevas: el repositorio ya tiene las $($archivos.Count)"
    }
    else {
        & git -C $repoRaiz commit -m "Sube las fotos de productos para migrar a la PC servidor ($($archivos.Count) fotos)"
        if ($LASTEXITCODE -ne 0) {
            throw "git commit fallo (codigo $LASTEXITCODE). Si se queja de la identidad: git config --global user.name ... / user.email ..."
        }
        Escribir-Ok "commit creado ($($pendiente.Count) archivos)"
    }

    # --- 4) Push -------------------------------------------------------------
    Escribir-Paso "[4/4] Subiendo a GitHub..."

    & git -C $repoRaiz push
    if ($LASTEXITCODE -ne 0) {
        throw "git push fallo (codigo $LASTEXITCODE). Si dice 'rejected / non-fast-forward', correr antes: git pull --rebase. Si dice 'could not read Username', vencio el token del remoto."
    }
    Escribir-Ok "fotos subidas al repositorio"

    Write-Host ""
    Write-Host "  -------------------------------------------------------" -ForegroundColor White
    Write-Host "  Ahora, en la PC servidor:" -ForegroundColor White
    Write-Host ""
    Write-Host "    1) Si el proyecto todavia no esta ahi:"
    Write-Host "         git clone <url del repo> ceramica_final"
    Write-Host "       El clone ya trae las fotos, no hace falta nada mas."
    Write-Host ""
    Write-Host "    2) Si el proyecto ya esta copiado:"
    Write-Host "         respaldo\traer_fotos.bat"
    Write-Host ""
    Write-Host "  FALTA LA BASE DE DATOS. Las fotos solas son archivos que" -ForegroundColor Yellow
    Write-Host "  nadie referencia: sin la base no hay catalogo. La base NO" -ForegroundColor Yellow
    Write-Host "  va por el repositorio, que es publico." -ForegroundColor Yellow
    Write-Host "  Ver docs/respaldo_y_migracion.md seccion 3.5." -ForegroundColor Yellow
    Write-Host "  -------------------------------------------------------" -ForegroundColor White
    Write-Host ""
}
catch {
    Escribir-Error-Fatal $_.Exception.Message
    exit 1
}

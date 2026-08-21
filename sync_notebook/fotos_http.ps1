# ============================================================================
#  Copia de las fotos de productos servidor -> notebook, por HTTP.
#
#  Por que HTTP y no una carpeta compartida:
#  el proyecto vive dentro de C:\Users\<usuario> en la PC servidor, y el ACL
#  NTFS de esa carpeta solo incluye a SYSTEM, Administradores y al usuario
#  duenio del perfil. Compartir backend\media con permiso "Todos: Leer" no
#  alcanza — NTFS manda sobre el permiso del recurso compartido, y ademas
#  Windows 11 bloquea el acceso invitado por SMB. Desde la notebook, que
#  entra con otra cuenta de Windows, la carpeta da "acceso denegado" y el
#  sync termina dejando el catalogo completo con TODAS las fotos rotas.
#
#  El servidor ya publica esos mismos archivos en http://<servidor>:8000/media/
#  (Django los sirve siempre, ver backend/config/urls.py). Bajarlos por ahi no
#  necesita cuentas de Windows, ni permisos NTFS, ni SMB.
#
#  Este archivo solo define funciones; lo carga sync_notebook.ps1.
# ============================================================================

# Devuelve las rutas relativas de todas las fotos segun la base YA restaurada
# en la notebook (ej. "productos/acc-001/foto.jpg"). Es la lista de lo que
# tiene que existir en disco: si algo no esta aca, sobra.
function Obtener-RutasFotos {
    param(
        [string] $Psql,
        [string] $DbNombre,
        [string] $DbUsuario,
        [string] $DbPuerto
    )

    $consulta = @"
SELECT imagen FROM imagenes_producto WHERE imagen IS NOT NULL AND imagen <> ''
UNION
SELECT imagen FROM imagenes_variante WHERE imagen IS NOT NULL AND imagen <> ''
"@

    # stderr de psql no debe volverse un error terminante: el resultado real
    # lo da $LASTEXITCODE (mismo criterio que Invoke-Nativo en sync_notebook.ps1).
    $previo = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $salida = & $Psql --host=localhost --port=$DbPuerto --username=$DbUsuario `
                          --dbname=$DbNombre --tuples-only --no-align `
                          --set=ON_ERROR_STOP=1 --command=$consulta 2>&1
    }
    finally { $ErrorActionPreference = $previo }

    if ($LASTEXITCODE -ne 0) {
        throw "psql no pudo leer la lista de fotos (codigo $LASTEXITCODE): $salida"
    }

    return @($salida | ForEach-Object { $_.ToString().Trim() } | Where-Object { $_ })
}

# Descarga lo que falte y borra lo que sobre. Devuelve un objeto con los
# contadores para que quien llama decida como loguearlo.
function Sincronizar-FotosHttp {
    param(
        [string]   $MediaUrl,
        [string]   $MediaLocal,
        [string[]] $Rutas
    )

    $res = [pscustomobject]@{
        Total       = $Rutas.Count
        Descargadas = 0
        Fallidas    = 0
        Borradas    = 0
        YaEstaban   = 0
    }

    # Guarda: sin lista no se toca nada. Si la consulta fallo o el catalogo
    # vino vacio, borrar "lo que sobra" seria borrar todas las fotos.
    if ($res.Total -eq 0) { return $res }

    if (-not (Test-Path $MediaLocal)) {
        New-Item -ItemType Directory -Path $MediaLocal -Force | Out-Null
    }

    $base = $MediaUrl.TrimEnd('/')
    $esperados = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $wc = New-Object System.Net.WebClient

    try {
        foreach ($ruta in $Rutas) {
            $relativa = $ruta -replace '/', '\'
            $destino  = Join-Path $MediaLocal $relativa
            [void]$esperados.Add($destino)

            if (Test-Path $destino) { $res.YaEstaban++; continue }

            # Django nunca reescribe un archivo existente: si se cambia la
            # foto de un producto, guarda una ruta nueva. Por eso alcanza con
            # "si el archivo ya esta, no lo bajo de nuevo" — no hace falta
            # comparar tamanios ni fechas contra el servidor en cada corrida.
            $carpeta = Split-Path -Parent $destino
            if (-not (Test-Path $carpeta)) {
                New-Item -ItemType Directory -Path $carpeta -Force | Out-Null
            }

            $url = $base + '/' + (($ruta -split '/' | ForEach-Object { [Uri]::EscapeDataString($_) }) -join '/')

            try {
                $wc.DownloadFile($url, $destino)
                $res.Descargadas++
            }
            catch {
                $res.Fallidas++
                Remove-Item $destino -ErrorAction SilentlyContinue
            }
        }
    }
    finally {
        $wc.Dispose()
    }

    # Espejo: sacar de la notebook lo que ya no esta en el servidor, para que
    # las fotos viejas no se acumulen para siempre. Mismo criterio con el que
    # el sync recrea la base de cero en cada corrida.
    #
    # Solo se borra si la descarga vino limpia: con fallas de red a medio
    # camino, la lista de "esperados" sigue siendo valida, pero preferimos no
    # tocar nada hasta que una corrida completa confirme el estado real.
    if ($res.Fallidas -eq 0) {
        Get-ChildItem $MediaLocal -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { -not $esperados.Contains($_.FullName) } |
            ForEach-Object {
                Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
                $res.Borradas++
            }

        # Carpetas de productos que quedaron vacias despues de borrar
        Get-ChildItem $MediaLocal -Recurse -Directory -ErrorAction SilentlyContinue |
            Sort-Object { $_.FullName.Length } -Descending |
            Where-Object { -not (Get-ChildItem $_.FullName -Force -ErrorAction SilentlyContinue) } |
            ForEach-Object { Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue }
    }

    return $res
}

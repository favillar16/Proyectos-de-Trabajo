# Funciones compartidas por respaldo.ps1 y restaurar.ps1.
# Se cargan con dot-sourcing:  . "$PSScriptRoot\_comun.ps1"
#
# Criterio general: la configuración de la base NO se duplica acá. Se lee
# siempre de backend\.env, que es la única fuente de verdad que ya usa Django
# (config/settings.py, DATABASES). Así un respaldo nunca apunta a una base
# distinta de la que el sistema está usando de verdad.

function Leer-EnvBackend {
    <#
        Lee backend\.env como pares CLAVE=VALOR y devuelve un hashtable.
        Mismo parseo simple que sync_notebook.ps1 — alcanza porque el .env
        del proyecto no usa comillas ni valores multilínea.
    #>
    param([Parameter(Mandatory = $true)][string]$RepoRaiz)

    $envPath = Join-Path $RepoRaiz 'backend\.env'
    if (-not (Test-Path $envPath)) {
        throw "No se encontró $envPath. Copiar backend\.env.example como backend\.env y completarlo antes de respaldar o restaurar."
    }

    $cfg = @{}
    Get-Content $envPath | ForEach-Object {
        $l = $_.Trim()
        if ($l -and -not $l.StartsWith('#') -and $l.Contains('=')) {
            $k, $v = $l.Split('=', 2)
            $cfg[$k.Trim()] = $v.Trim()
        }
    }
    return $cfg
}

function Valor-O-Default {
    param($Cfg, [string]$Clave, [string]$Default)
    if ($Cfg.ContainsKey($Clave) -and $Cfg[$Clave]) { return $Cfg[$Clave] }
    return $Default
}

function Resolver-BinariosPg {
    <#
        Devuelve las rutas de pg_dump.exe y psql.exe.
        Primero busca en el PATH (setup.bat ya exige que estén ahí); si no
        aparecen, prueba las carpetas típicas de instalación de PostgreSQL en
        Windows, para que el script funcione igual en una PC recién armada
        donde todavía no se tocó el PATH.
    #>
    $pgDump = $null
    $psql   = $null

    $enPath = Get-Command pg_dump.exe -ErrorAction SilentlyContinue
    if ($enPath) {
        $pgDump = $enPath.Source
        $psql   = (Get-Command psql.exe -ErrorAction SilentlyContinue).Source
    }

    if (-not $pgDump) {
        $candidatos = Get-ChildItem 'C:\Program Files\PostgreSQL' -Directory -ErrorAction SilentlyContinue |
                      Sort-Object Name -Descending
        foreach ($c in $candidatos) {
            $bin = Join-Path $c.FullName 'bin'
            if (Test-Path (Join-Path $bin 'pg_dump.exe')) {
                $pgDump = Join-Path $bin 'pg_dump.exe'
                $psql   = Join-Path $bin 'psql.exe'
                break
            }
        }
    }

    if (-not $pgDump -or -not $psql) {
        throw "No se encontraron pg_dump.exe / psql.exe. Instalar PostgreSQL 15 y agregar su carpeta bin al PATH (ej. C:\Program Files\PostgreSQL\15\bin)."
    }

    return @{ PgDump = $pgDump; Psql = $psql }
}

function Formatear-Tamano {
    param([long]$Bytes)
    if ($Bytes -ge 1GB) { return "{0:N2} GB" -f ($Bytes / 1GB) }
    if ($Bytes -ge 1MB) { return "{0:N1} MB" -f ($Bytes / 1MB) }
    if ($Bytes -ge 1KB) { return "{0:N1} KB" -f ($Bytes / 1KB) }
    return "$Bytes bytes"
}

function Tamano-Carpeta {
    param([string]$Ruta)
    if (-not (Test-Path $Ruta)) { return 0 }
    $medida = Get-ChildItem $Ruta -Recurse -File -ErrorAction SilentlyContinue |
              Measure-Object -Property Length -Sum
    if ($medida.Sum) { return [long]$medida.Sum }
    return 0
}

function Escribir-Paso {
    param([string]$Texto)
    Write-Host ""
    Write-Host "  $Texto" -ForegroundColor Cyan
}

function Escribir-Ok {
    param([string]$Texto)
    Write-Host "  OK: $Texto" -ForegroundColor Green
}

function Escribir-Error-Fatal {
    param([string]$Texto)
    Write-Host ""
    Write-Host "  ERROR: $Texto" -ForegroundColor Red
    Write-Host ""
}

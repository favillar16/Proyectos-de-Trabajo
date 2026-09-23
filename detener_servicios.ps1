# ==============================================================================
#  Oga Pora - para daphne y Vite cuando corren ocultos en segundo plano
#  (los que arranca iniciar_servicios.ps1).
#
#  Usa el PID guardado en logs\<nombre>.pid. Si el archivo no esta o el PID
#  guardado ya no corresponde a nada vivo (por ejemplo, Windows se reinicio
#  de forma sucia y nunca se llego a limpiar), busca como respaldo que
#  proceso tiene el puerto abierto y mata ese.
#
#  Lo llama detener.bat. No es para doble clic directo.
# ==============================================================================

$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$logs = Join-Path $raiz 'logs'

function Detener($nombre, $puerto) {
    $pidFile = Join-Path $logs "$nombre.pid"
    $detenido = $false

    if (Test-Path $pidFile) {
        $procId = Get-Content $pidFile -ErrorAction SilentlyContinue
        if ($procId -and (Get-Process -Id $procId -ErrorAction SilentlyContinue)) {
            taskkill /PID $procId /T /F | Out-Null
            Write-Host "  $nombre detenido (PID $procId)."
            $detenido = $true
        }
        Remove-Item $pidFile -ErrorAction SilentlyContinue
    }

    if (-not $detenido) {
        $conexion = Get-NetTCPConnection -LocalPort $puerto -State Listen -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($conexion) {
            taskkill /PID $conexion.OwningProcess /T /F | Out-Null
            Write-Host "  $nombre detenido por puerto (PID $($conexion.OwningProcess)); no tenia PID guardado o estaba viejo."
            $detenido = $true
        }
    }

    if (-not $detenido) {
        Write-Host "  $nombre no estaba corriendo."
    }
}

Detener 'daphne' 8000
Detener 'vite' 5173
Detener 'sidecar' 8100

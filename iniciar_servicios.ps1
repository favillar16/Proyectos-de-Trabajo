# ==============================================================================
#  Oga Pora - arranca daphne y Vite ocultos, sin ventana propia.
#
#  Antes, iniciar.bat abria "start cmd /k ...": dos ventanas negras que
#  quedaban corriendo para siempre. El personal del local podia cerrarlas por
#  accidente creyendo que eran una ventana cualquiera, y eso tira el sistema
#  para todas las tablets a la vez. Con -WindowStyle Hidden no hay ventana ni
#  entrada en la barra de tareas que se pueda cerrar sin querer.
#
#  La salida de cada proceso va a logs\<nombre>.log (se acumula, con una
#  marca de fecha en cada arranque) y el PID del proceso lanzado queda en
#  logs\<nombre>.pid para que detener.bat sepa a cual matar despues -
#  matar "daphne" a mano es peligroso porque corre dentro de python.exe,
#  un nombre de proceso demasiado generico para buscarlo por nombre.
#
#  Lo llama iniciar.bat. No es para doble clic directo.
# ==============================================================================

$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$logs = Join-Path $raiz 'logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null

function Puerto-Ocupado($puerto) {
    return [bool](Get-NetTCPConnection -LocalPort $puerto -State Listen -ErrorAction SilentlyContinue)
}

function Iniciar-Oculto($nombre, $directorio, $comando, $puerto) {
    if (Puerto-Ocupado $puerto) {
        Write-Host "  $nombre ya esta corriendo (puerto $puerto ocupado). No se abre otro."
        return
    }

    $log = Join-Path $logs "$nombre.log"
    $pidFile = Join-Path $logs "$nombre.pid"

    "`n===== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') =====" | Out-File -FilePath $log -Append -Encoding utf8
    $lineaCompleta = "cd /d `"$directorio`" && $comando >> `"$log`" 2>&1"
    $proceso = Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', $lineaCompleta -WindowStyle Hidden -PassThru
    $proceso.Id | Out-File -FilePath $pidFile -Encoding ascii
    Write-Host "  $nombre iniciado en segundo plano (PID $($proceso.Id))."
}

# Dos endpoints, IPv4 e IPv6: los nombres de red (OGAPORA, ogapora.local)
# resuelven PRIMERO a IPv6, asi que escuchando solo en 0.0.0.0 el navegador
# intenta IPv6, no encuentra a nadie y da timeout.
Iniciar-Oculto 'daphne' (Join-Path $raiz 'backend') `
    'venv\Scripts\activate && daphne -e tcp:8000:interface=0.0.0.0 -e tcp6:8000:interface=\:\: config.asgi:application' `
    8000

Iniciar-Oculto 'vite' (Join-Path $raiz 'frontend') 'npm run dev' 5173

# Sidecar de facturacion electronica. Solo arranca si esta instalado: la
# tienda funciono meses sin el, y una PC recien reinstalada donde todavia no
# se corrio "npm install" en sidecar\ tiene que poder vender igual. Que no
# este no es un error - por eso avisa y sigue, no corta el arranque.
#
# Escucha en 127.0.0.1 solamente (ver sidecar\config.js): tiene la clave del
# certificado y firma cualquier XML que le manden, asi que no puede quedar
# expuesto a la red de las tablets.
$sidecar = Join-Path $raiz 'sidecar'
if (Test-Path (Join-Path $sidecar 'node_modules')) {
    Iniciar-Oculto 'sidecar' $sidecar 'npm start' 8100
} elseif (Test-Path (Join-Path $sidecar 'package.json')) {
    Write-Host "  sidecar sin instalar (falta 'npm install' en sidecar\). Se omite."
    Write-Host "  La facturacion electronica no transmite hasta que este levantado."
}

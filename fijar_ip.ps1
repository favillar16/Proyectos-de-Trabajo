# ============================================================================
#  Oga Pora - Fija la IP de la PC SERVIDOR sin depender del router
#
#  Plan B de la reserva DHCP: en vez de pedirle al router que siempre le de
#  la misma IP a esta PC, se la ponemos fija nosotros. Elegimos una direccion
#  ALTA (.250) porque el router reparte desde abajo (.3, .4, .7, .9, .13...),
#  asi que nunca va a llegar hasta ahi. Ademas, antes de tomarla el script
#  verifica que este libre.
#
#  Ejecutar como Administrador (usar fijar_ip.bat).
#  Para volver a DHCP: correr este mismo script con  -Deshacer
# ============================================================================

param(
    [string] $IP       = '192.168.100.250',
    [int]    $Prefijo  = 24,
    [string] $Gateway  = '192.168.100.1',
    [switch] $Deshacer
)

$ErrorActionPreference = 'Stop'

function Ok  ($m) { Write-Host "[OK]  $m" -ForegroundColor Green }
function Info($m) { Write-Host "[..]  $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "[!]   $m" -ForegroundColor Yellow }
function Bad ($m) { Write-Host "[X]   $m" -ForegroundColor Red }

$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $esAdmin) {
    Bad "Este script necesita permisos de Administrador."
    Bad "Cerrar esta ventana y usar fijar_ip.bat (doble clic)."
    Read-Host "Enter para salir"
    exit 1
}

# --- Encontrar el adaptador que hoy esta en la red del local ---------------
$actual = Get-NetIPAddress -AddressFamily IPv4 |
          Where-Object { $_.IPAddress -like '192.168.100.*' } |
          Select-Object -First 1

if (-not $actual) {
    Bad "Esta PC no esta conectada a la red 192.168.100.x."
    Bad "Conectarse a la WiFi del local y volver a correr el script."
    Read-Host "Enter para salir"
    exit 1
}

$idx   = $actual.InterfaceIndex
$alias = (Get-NetAdapter -InterfaceIndex $idx).Name
Write-Host ""
Write-Host "Adaptador : $alias" -ForegroundColor White
Write-Host "IP actual : $($actual.IPAddress)  ($($actual.PrefixOrigin))" -ForegroundColor White
Write-Host ""

# --- Modo deshacer: volver a DHCP ------------------------------------------
if ($Deshacer) {
    Info "Volviendo a DHCP..."
    Remove-NetRoute -InterfaceIndex $idx -DestinationPrefix '0.0.0.0/0' -Confirm:$false -ErrorAction SilentlyContinue
    Set-NetIPInterface -InterfaceIndex $idx -Dhcp Enabled
    Set-DnsClientServerAddress -InterfaceIndex $idx -ResetServerAddresses
    ipconfig /renew  | Out-Null
    $nueva = (Get-NetIPAddress -InterfaceIndex $idx -AddressFamily IPv4 | Select-Object -First 1).IPAddress
    Ok "El adaptador volvio a DHCP. IP actual: $nueva"
    Read-Host "Enter para cerrar"
    exit 0
}

# --- 1. Comprobar que la IP elegida este libre -----------------------------
Info "1. Comprobando que $IP este libre"
if ($actual.IPAddress -eq $IP) {
    Ok "Esta PC ya tiene $IP"
} else {
    $ocupada = $false
    if (Test-Connection -ComputerName $IP -Count 2 -Quiet -ErrorAction SilentlyContinue) { $ocupada = $true }
    $vecino = Get-NetNeighbor -IPAddress $IP -ErrorAction SilentlyContinue |
              Where-Object { $_.LinkLayerAddress -and $_.LinkLayerAddress -ne '00-00-00-00-00-00' }
    if ($vecino) { $ocupada = $true }
    if ($ocupada) {
        Bad "$IP ya esta en uso por otro equipo. NO se cambio nada."
        Bad "Volver a correr eligiendo otra, por ejemplo:  .\fijar_ip.ps1 -IP 192.168.100.249"
        Read-Host "Enter para salir"
        exit 1
    }
    Ok "$IP esta libre"
}

# --- 2. Aplicar la configuracion fija --------------------------------------
Info "2. Fijando la direccion (la red se corta un instante)"
Remove-NetRoute   -InterfaceIndex $idx -DestinationPrefix '0.0.0.0/0' -Confirm:$false -ErrorAction SilentlyContinue
Get-NetIPAddress  -InterfaceIndex $idx -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
Set-NetIPInterface -InterfaceIndex $idx -Dhcp Disabled
New-NetIPAddress   -InterfaceIndex $idx -IPAddress $IP -PrefixLength $Prefijo -DefaultGateway $Gateway | Out-Null
Set-DnsClientServerAddress -InterfaceIndex $idx -ServerAddresses @($Gateway, '8.8.8.8')
Start-Sleep -Seconds 3
Ok "IP fija $IP / mascara /$Prefijo / puerta de enlace $Gateway"

# --- 3. Verificar que siga andando todo ------------------------------------
Info "3. Verificando"
$ipFinal = (Get-NetIPAddress -InterfaceIndex $idx -AddressFamily IPv4 | Select-Object -First 1)
Write-Host ("      IP        : " + $ipFinal.IPAddress + "  (" + $ipFinal.PrefixOrigin + ")")

if (Test-Connection -ComputerName $Gateway -Count 2 -Quiet -ErrorAction SilentlyContinue) {
    Ok "Llega al router ($Gateway)"
} else {
    Warn "No responde el router al ping (este router no contesta ping, puede ser normal)"
}

try {
    $r = Invoke-WebRequest -Uri 'http://192.168.100.1/web_whw/' -UseBasicParsing -TimeoutSec 15
    Ok "La red local responde"
} catch {
    Warn "No se pudo confirmar la red local por HTTP"
}

try {
    Resolve-DnsName -Name 'google.com' -QuickTimeout -ErrorAction Stop | Out-Null
    Ok "Internet / DNS funcionando"
} catch {
    Warn "Sin resolucion DNS. Si el local no tiene internet, es esperable."
}

foreach ($p in @(5173, 8000)) {
    if (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue) {
        Ok "El sistema esta escuchando en el puerto $p"
    } else {
        Warn "Nadie escucha en el puerto $p - falta arrancar iniciar.bat"
    }
}

Write-Host ""
Write-Host "=== Listo ===" -ForegroundColor White
Write-Host "  El sistema queda siempre en:  http://$IP`:5173"
Write-Host "  Esta direccion ya no cambia aunque se corte la luz o se"
Write-Host "  reinicie el router."
Write-Host ""
Write-Host "  Para volver a DHCP:  fijar_ip.bat deshacer" -ForegroundColor DarkGray
Write-Host ""
Read-Host "Enter para cerrar"

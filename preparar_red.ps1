# ============================================================================
#  Oga Pora - Preparacion de la PC SERVIDOR para la red del local
#  Ejecutar UNA sola vez, como Administrador (usar preparar_red.bat).
#  Es idempotente: se puede volver a correr sin romper nada.
# ============================================================================

$ErrorActionPreference = 'Stop'

function Ok  ($m) { Write-Host "[OK]  $m" -ForegroundColor Green }
function Info($m) { Write-Host "[..]  $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "[!]   $m" -ForegroundColor Yellow }
function Bad ($m) { Write-Host "[X]   $m" -ForegroundColor Red }

$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $esAdmin) {
    Bad "Este script necesita permisos de Administrador."
    Bad "Cerrar esta ventana y usar preparar_red.bat (doble clic)."
    Read-Host "Enter para salir"
    exit 1
}

$raiz   = Split-Path -Parent $MyInvocation.MyCommand.Path
$media  = Join-Path $raiz 'backend\media'
$subred = '192.168.100.0/24'

Write-Host ""
Write-Host "=== Oga Pora - preparacion de red del servidor ===" -ForegroundColor White
Write-Host ""

# --- 1. Marcar la red del local como Privada -------------------------------
Info "1. Categoria de red"
$perfiles = Get-NetConnectionProfile | Where-Object { $_.IPv4Connectivity -eq 'Internet' -or $_.IPv4Connectivity -eq 'LocalNetwork' }
foreach ($p in $perfiles) {
    if ($p.NetworkCategory -ne 'Private') {
        Set-NetConnectionProfile -InterfaceIndex $p.InterfaceIndex -NetworkCategory Private
        Ok "Red '$($p.Name)' ($($p.InterfaceAlias)) -> Privada"
    } else {
        Ok "Red '$($p.Name)' ($($p.InterfaceAlias)) ya estaba Privada"
    }
}

# --- 2. Abrir los puertos del sistema en el firewall ------------------------
Info "2. Reglas de firewall"
# El 5432 es solo para el espejo de la notebook, que se conecta a PostgreSQL
# por la red con el rol de SOLO LECTURA notebook_sync. Queda limitado al perfil
# Private (la red del local) y sigue exigiendo contrasena: pg_hba.conf usa
# scram-sha-256 para la subred. Sin esta regla el sync de la notebook falla con
# "responde ping pero no el puerto Postgres 5432".
$reglas = @(
    @{ Nombre = 'Oga Pora - Frontend (5173)'; Puerto = 5173 },
    @{ Nombre = 'Oga Pora - Backend (8000)';  Puerto = 8000 },
    @{ Nombre = 'Oga Pora - PostgreSQL (5432)'; Puerto = 5432 }
)
foreach ($r in $reglas) {
    $existente = Get-NetFirewallRule -DisplayName $r.Nombre -ErrorAction SilentlyContinue
    if ($existente) {
        Enable-NetFirewallRule -DisplayName $r.Nombre
        Ok "Regla '$($r.Nombre)' ya existia (habilitada)"
    } else {
        New-NetFirewallRule -DisplayName $r.Nombre -Direction Inbound -Protocol TCP `
            -LocalPort $r.Puerto -Action Allow -Profile Private | Out-Null
        Ok "Regla '$($r.Nombre)' creada"
    }
}

# --- 3. Que el servidor no se suspenda -------------------------------------
Info "3. Energia (el servidor no se puede dormir)"
powercfg /change standby-timeout-ac 0   | Out-Null
powercfg /change hibernate-timeout-ac 0 | Out-Null
powercfg /change disk-timeout-ac 0      | Out-Null
Ok "Suspension, hibernacion y apagado de disco desactivados con corriente alterna"
Ok "La pantalla se sigue apagando sola (eso no afecta al sistema)"

# --- 4. Compartir backend\media en solo lectura (opcional) -----------------
# Desde el 21/08/2026 la notebook baja las fotos por HTTP y no necesita esto.
# Se deja igual: es una via alternativa y la primera copia es mas rapida.
Info "4. Carpeta de fotos compartida"
if (-not (Test-Path $media)) {
    Warn "No se encontro $media - se saltea"
} else {
    $todos = (New-Object System.Security.Principal.SecurityIdentifier('S-1-1-0')).Translate([System.Security.Principal.NTAccount]).Value
    if (Get-SmbShare -Name 'media' -ErrorAction SilentlyContinue) {
        Ok "El recurso compartido 'media' ya existia"
    } else {
        New-SmbShare -Name 'media' -Path $media -ReadAccess $todos -Description 'Oga Pora - fotos de productos (solo lectura)' | Out-Null
        Ok "Compartido como \\$env:COMPUTERNAME\media (solo lectura)"
    }
}

# --- 5. PostgreSQL: aceptar conexiones de la red local ---------------------
Info "5. PostgreSQL - acceso desde la red local (lo necesita la notebook)"
$hba = 'C:\Program Files\PostgreSQL\15\data\pg_hba.conf'
if (-not (Test-Path $hba)) {
    Warn "No se encontro $hba - se saltea"
} else {
    $contenido = Get-Content $hba -Raw
    if ($contenido -match [regex]::Escape($subred)) {
        Ok "pg_hba.conf ya tenia la linea de $subred"
    } else {
        Copy-Item $hba "$hba.bak_$(Get-Date -Format yyyyMMdd_HHmmss)"
        Add-Content -Path $hba -Value "`r`n# Oga Pora - red local del negocio`r`nhost    all             all             $subred            scram-sha-256"
        Restart-Service postgresql-x64-15
        Ok "Linea agregada y servicio de PostgreSQL reiniciado (copia .bak guardada)"
    }
}

# --- 6. Resumen ------------------------------------------------------------
Write-Host ""
Write-Host "=== Estado final ===" -ForegroundColor White
$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1)
Write-Host ("  Hostname       : " + $env:COMPUTERNAME)
Write-Host ("  IP del servidor: " + $ip.IPAddress + "  (" + $ip.InterfaceAlias + ")")
Write-Host ("  MAC            : " + (Get-NetAdapter -InterfaceIndex $ip.InterfaceIndex).MacAddress + "   <- para la reserva en el router")
Get-NetConnectionProfile | Where-Object { $_.InterfaceIndex -eq $ip.InterfaceIndex } | ForEach-Object {
    Write-Host ("  Categoria red  : " + $_.NetworkCategory)
}
Write-Host ""
Write-Host "Falta hacer a mano:" -ForegroundColor Yellow
Write-Host "  - Reservar la IP de arriba en el router (DHCP -> reserva por MAC)"
Write-Host "  - Cambiar las contrasenas de admin/cajero/deposito/vendedor (siguen en demo2025)"
Write-Host "  - Desde otro equipo: Test-NetConnection -ComputerName $($ip.IPAddress) -Port 5173"
Write-Host ""
Read-Host "Enter para cerrar"

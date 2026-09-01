# Resolver — encuentra a la PC servidor sin depender de una IP fija.
#
# Se carga con dot-sourcing desde los scripts que lo necesitan:
#     . "$PSScriptRoot\resolver_servidor.ps1"
#
# Por qué existe: en el local no hay acceso al panel del router, así que no se
# puede reservar la IP del servidor por DHCP. Está fijada desde la propia PC
# (fijar_ip.ps1), pero si el router se reemplaza o se resetea, la subred entera
# cambia y esa IP deja de existir. Nada debería quedar atado a un número.
#
# Dos preguntas distintas, que se resuelven por separado:
#   1. ¿Estamos adentro del local?  -> por red WiFi (SSID y BSSID del AP)
#   2. ¿Dónde está el servidor?     -> por nombre de red, cache, o barrido
#
# La (1) importa porque la notebook se lleva afuera: si no estamos en la red
# del negocio no tiene sentido ni intentar, y evita que un servidor ajeno con
# el puerto 8000 abierto se haga pasar por el nuestro.

$ErrorActionPreference = 'Stop'

# ─── 1. ¿Estamos en la red del local? ────────────────────────────────────────

<#
.SYNOPSIS
Devuelve la red WiFi actual: SSID y BSSID del punto de acceso.

.DESCRIPTION
El BSSID es la MAC de la antena del router. No hace falta entrar al panel del
router para leerla: la reporta el propio adaptador WiFi. Es un identificador
más fuerte que el SSID, que cualquiera puede copiar.
Devuelve $null si no hay WiFi conectado (por ejemplo, si la PC está por cable).
#>
function Get-RedWifiActual {
    try {
        $salida = netsh wlan show interfaces 2>$null
    } catch {
        return $null
    }
    if (-not $salida) { return $null }

    $ssid  = $null
    $bssid = $null
    foreach ($linea in $salida) {
        # "^\s*SSID" no matchea "AP BSSID"/"BSSID de AP" porque esas empiezan
        # con otra palabra. El nombre del campo está localizado, el orden no.
        if (-not $ssid  -and $linea -match '^\s*SSID\s*:\s*(.+?)\s*$')  { $ssid  = $Matches[1] }
        if (-not $bssid -and $linea -match 'BSSID.*:\s*([0-9a-fA-F:]{17})') { $bssid = $Matches[1].ToLower() }
    }
    if (-not $ssid) { return $null }
    return [pscustomobject]@{ SSID = $ssid; BSSID = $bssid }
}

<#
.SYNOPSIS
$true si el equipo está en la red del local.

.PARAMETER SsidEsperado
Nombre de la red WiFi del negocio (ej: "OGA PORA").

.PARAMETER BssidEsperado
MAC del AP, opcional. Si se completa, tiene que coincidir además del SSID.
Se anota la primera vez con:  (Get-RedWifiActual).BSSID

.PARAMETER PermitirCable
Si el equipo está por cable no hay SSID que mirar. Con esto en $true se lo
da por adentro y la decisión final queda en manos de la sonda de identidad.
#>
function Test-EnRedDelLocal {
    param(
        [string] $SsidEsperado,
        [string] $BssidEsperado = '',
        [bool]   $PermitirCable = $true
    )

    $red = Get-RedWifiActual
    if (-not $red) { return $PermitirCable }
    if (-not $SsidEsperado) { return $true }

    if ($red.SSID -ne $SsidEsperado) { return $false }
    if ($BssidEsperado -and $red.BSSID -and $red.BSSID -ne $BssidEsperado.ToLower()) {
        # Mismo nombre de red pero otra antena: no es nuestro local.
        return $false
    }
    return $true
}

# ─── 2. ¿Dónde está el servidor? ─────────────────────────────────────────────

<#
.SYNOPSIS
Pregunta la identidad a un host. Devuelve el objeto de /api/v1/salud/ o $null.

.DESCRIPTION
Confirma que del otro lado hay un Oga Porã y no cualquier equipo con el
puerto abierto. Con -RolEsperado 'servidor' además evita que la notebook se
sincronice contra sí misma o contra otro espejo.
#>
function Get-IdentidadNodo {
    param(
        [Parameter(Mandatory)] [string] $Host_,
        [int]    $Puerto = 8000,
        [int]    $TimeoutMs = 2500,
        [string] $RolEsperado = ''
    )
    try {
        $req = [System.Net.HttpWebRequest]::Create("http://${Host_}:${Puerto}/api/v1/salud/")
        $req.Proxy = $null           # el proxy del sistema no aplica en LAN
        $req.Timeout = $TimeoutMs
        $req.ReadWriteTimeout = $TimeoutMs
        $resp = $req.GetResponse()
        $texto = (New-Object IO.StreamReader($resp.GetResponseStream())).ReadToEnd()
        $resp.Close()
        $datos = $texto | ConvertFrom-Json
        if ($datos.sistema -ne 'oga-pora') { return $null }
        if ($RolEsperado -and $datos.rol -ne $RolEsperado) { return $null }
        return $datos
    } catch {
        return $null
    }
}

<#
.SYNOPSIS
Direcciones IPv4 de las subredes donde está este equipo, sin las link-local.

.DESCRIPTION
Las 169.254.x son direcciones de adaptadores que quedaron sin DHCP (esta
notebook tiene varias, de placas que no se usan). Barrerlas es tiempo perdido.
#>
function Get-SubredesLocales {
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1' } |
        ForEach-Object { $_.IPAddress }
}

<#
.SYNOPSIS
Los pocos candidatos donde conviene buscar primero: octetos habituales + ARP.

.DESCRIPTION
No se filtran por ping a propósito. Medido en esta red, el servidor por WiFi
pierde pings de forma intermitente (entra en ahorro de energía), así que usar
el ping como filtro lo hace desaparecer justo cuando lo estamos buscando. Son
pocas direcciones: se les pregunta HTTP directo y listo.

La tabla ARP lista los equipos con los que este ya habló recién, así que el
servidor casi siempre está entre ellos.
#>
function Get-CandidatosProbables {
    param([Parameter(Mandatory)] [string] $IpPropia)

    $partes  = $IpPropia.Split('.')
    $prefijo = "$($partes[0]).$($partes[1]).$($partes[2])"
    $mio     = [int]$partes[3]

    $probables = @(250, 100, 10, 2, 200, 150)
    $enArp = @()
    try {
        $enArp = (arp -a) |
            Select-String "$([regex]::Escape($prefijo))\.(\d{1,3})" -AllMatches |
            ForEach-Object { $_.Matches } | ForEach-Object { [int]$_.Groups[1].Value }
    } catch {}

    @($probables) + @($enArp) |
        Where-Object { $_ -ne $mio -and $_ -ge 1 -and $_ -le 254 } |
        Select-Object -Unique |
        ForEach-Object { "$prefijo.$_" }
}

<#
.SYNOPSIS
Resto de la subred que contesta ping. Solo se usa si los probables fallaron.

.DESCRIPTION
Test-Connection es secuencial y espera ~1s por host muerto: 254 direcciones son
más de 4 minutos, impensable en una tarea que corre cada 5. Con SendPingAsync
los 254 pings salen juntos y termina en poco más de un segundo.
#>
function Get-HostsVivos {
    param(
        [Parameter(Mandatory)] [string] $IpPropia,
        [int] $TimeoutPingMs = 1000
    )

    $partes  = $IpPropia.Split('.')
    $prefijo = "$($partes[0]).$($partes[1]).$($partes[2])"
    $mio     = [int]$partes[3]
    $orden   = 1..254 | Where-Object { $_ -ne $mio }

    $ping = @{}
    foreach ($o in $orden) {
        $ip = "$prefijo.$o"
        $ping[$ip] = (New-Object System.Net.NetworkInformation.Ping).SendPingAsync($ip, $TimeoutPingMs)
    }
    try {
        [System.Threading.Tasks.Task]::WaitAll(
            [System.Threading.Tasks.Task[]]$ping.Values, $TimeoutPingMs + 2000) | Out-Null
    } catch {}

    # Se respeta el orden de la subred, no el de llegada de los pings.
    $vivos = New-Object System.Collections.Generic.List[string]
    foreach ($o in $orden) {
        $ip = "$prefijo.$o"
        $t = $ping[$ip]
        if ($t.IsCompleted -and -not $t.IsFaulted -and $t.Result.Status -eq 'Success') { $vivos.Add($ip) }
    }
    return $vivos
}

<#
.SYNOPSIS
Encuentra la PC servidor y devuelve su host, identidad y cómo se la encontró.

.DESCRIPTION
Prueba en orden, del más barato al más caro:
  1. -HostFijo, si alguien lo puso a mano en la configuración.
  2. El último servidor que funcionó (archivo de cache).
  3. Los nombres de red: mDNS (.local) y NetBIOS. Windows los resuelve solo.
  4. Direcciones probables (octetos típicos + tabla ARP) por HTTP directo.
  5. Barrido del resto de la subred, filtrando por ping.

Devuelve $null si no hay servidor a la vista.
#>
function Find-Servidor {
    param(
        [string]   $HostFijo = '',
        [string[]] $Nombres = @('ogapora.local', 'ogapora'),
        [int]      $Puerto = 8000,
        [string]   $ArchivoCache = '',
        [string]   $RolEsperado = 'servidor',
        [bool]     $Barrer = $true
    )

    function Devolver($nodoHost, $identidad, $via) {
        if ($ArchivoCache) {
            try {
                $dir = Split-Path -Parent $ArchivoCache
                if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
                @{ host = $nodoHost; nombre = $identidad.nombre; visto = (Get-Date).ToString('o') } |
                    ConvertTo-Json | Set-Content -Path $ArchivoCache -Encoding utf8
            } catch {}
        }
        [pscustomobject]@{ Host = $nodoHost; Identidad = $identidad; Via = $via }
    }

    # 1 — configurado a mano
    if ($HostFijo -and $HostFijo -ne 'auto') {
        $id = Get-IdentidadNodo -Host_ $HostFijo -Puerto $Puerto -RolEsperado $RolEsperado
        if ($id) { return Devolver $HostFijo $id 'configurado' }
    }

    # 2 — último conocido
    if ($ArchivoCache -and (Test-Path $ArchivoCache)) {
        try {
            $guardado = (Get-Content $ArchivoCache -Raw | ConvertFrom-Json).host
            if ($guardado) {
                $id = Get-IdentidadNodo -Host_ $guardado -Puerto $Puerto -RolEsperado $RolEsperado
                if ($id) { return Devolver $guardado $id 'cache' }
            }
        } catch {}
    }

    # 3 — nombres de red
    foreach ($n in $Nombres) {
        if (-not $n) { continue }
        $id = Get-IdentidadNodo -Host_ $n -Puerto $Puerto -RolEsperado $RolEsperado
        if ($id) { return Devolver $n $id 'nombre' }
    }

    # 4 — barrido. Último recurso: es el único camino si cambió la subred entera
    # (router nuevo) y encima falla la resolución de nombres.
    if ($Barrer) {
        $subredes = @(Get-SubredesLocales)

        # 4a — puñado de direcciones probables (octetos típicos + tabla ARP),
        # preguntando HTTP directo: son pocas y el ping acá no es confiable.
        $yaProbados = @{}
        foreach ($propia in $subredes) {
            foreach ($cand in Get-CandidatosProbables $propia) {
                if ($yaProbados[$cand]) { continue }
                $yaProbados[$cand] = $true
                $id = Get-IdentidadNodo -Host_ $cand -Puerto $Puerto -TimeoutMs 900 -RolEsperado $RolEsperado
                if ($id) { return Devolver $cand $id 'probables' }
            }
        }

        # 4b — el resto de la subred, esta vez sí filtrando por ping para no
        # abrir 254 sockets HTTP.
        foreach ($propia in $subredes) {
            foreach ($cand in Get-HostsVivos $propia) {
                if ($yaProbados[$cand]) { continue }
                $yaProbados[$cand] = $true
                $id = Get-IdentidadNodo -Host_ $cand -Puerto $Puerto -TimeoutMs 1200 -RolEsperado $RolEsperado
                if ($id) { return Devolver $cand $id 'barrido' }
            }
        }
    }

    return $null
}

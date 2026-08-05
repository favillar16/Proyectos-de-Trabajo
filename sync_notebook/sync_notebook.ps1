# Sincroniza la base de datos LOCAL de la notebook con la de la PC servidor
# del local, cuando ambas están en la misma red.
#
# La notebook es un ESPEJO DE SOLO LECTURA: este script siempre copia
# servidor -> notebook, nunca al revés. Si la notebook está fuera del local
# (sin conexión al servidor), el script no hace nada y la notebook se queda
# con los datos de la última sincronización.
#
# Pensado para correr cada pocos minutos vía el Programador de tareas de
# Windows (ver instalar_tarea_programada.bat), no a mano.

$ErrorActionPreference = 'Stop'
$carpeta = Split-Path -Parent $MyInvocation.MyCommand.Path
$configPath = Join-Path $carpeta 'config.env'
$logDir     = Join-Path $carpeta 'logs'
$estadoDir  = Join-Path $carpeta 'estado'
$tmpDir     = Join-Path $carpeta 'tmp'
$logFile    = Join-Path $logDir 'sync.log'
$lockFile   = Join-Path $tmpDir 'sync.lock'

foreach ($d in @($logDir, $estadoDir, $tmpDir)) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

function Log($mensaje) {
    $linea = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $mensaje
    Add-Content -Path $logFile -Value $linea
    # Evita que el log crezca sin límite en un dispositivo que nadie revisa seguido
    if ((Get-Item $logFile).Length -gt 2MB) {
        $ultimas = Get-Content $logFile -Tail 2000
        Set-Content -Path $logFile -Value $ultimas
    }
}

function Escribir-Estado($status, $detalle) {
    $estado = @{
        timestamp = (Get-Date).ToString('o')
        status    = $status
        detalle   = $detalle
    }
    $estado | ConvertTo-Json | Set-Content -Path (Join-Path $estadoDir 'last_sync.json')
}

# ─── Evitar sincronizaciones superpuestas ────────────────────────────────────
if (Test-Path $lockFile) {
    $edadMin = ((Get-Date) - (Get-Item $lockFile).LastWriteTime).TotalMinutes
    if ($edadMin -lt 10) {
        Log "Ya hay un sync en curso (lock de hace $([math]::Round($edadMin,1)) min) — se omite esta corrida."
        exit 0
    }
    Log "Lock viejo (hace $([math]::Round($edadMin,1)) min), se ignora y continúa."
}
New-Item -ItemType File -Path $lockFile -Force | Out-Null
try {

    if (-not (Test-Path $configPath)) {
        Log "ERROR: falta config.env (copiar config.env.example y completar). Se aborta."
        Escribir-Estado 'error' 'Falta config.env'
        exit 1
    }

    # ─── Cargar config.env (KEY=VALOR, líneas con # son comentario) ─────────
    $cfg = @{}
    Get-Content $configPath | ForEach-Object {
        $l = $_.Trim()
        if ($l -and -not $l.StartsWith('#') -and $l.Contains('=')) {
            $k, $v = $l.Split('=', 2)
            $cfg[$k.Trim()] = $v.Trim()
        }
    }

    $pgBin = $cfg['PG_BIN_DIR']
    $pgDump = if ($pgBin) { Join-Path $pgBin 'pg_dump.exe' } else { 'pg_dump' }
    $psql   = if ($pgBin) { Join-Path $pgBin 'psql.exe' }   else { 'psql' }

    # ─── ¿Estamos en el local? (servidor alcanzable) ─────────────────────────
    $host_ = $cfg['SERVIDOR_HOST']
    $puertoDb = $cfg['SERVIDOR_DB_PUERTO']

    $ping = Test-Connection -ComputerName $host_ -Count 1 -Quiet -ErrorAction SilentlyContinue
    if (-not $ping) {
        Log "Servidor $host_ no responde — notebook fuera del local, se omite sync."
        Escribir-Estado 'omitido' "Servidor $host_ no responde"
        exit 0
    }

    $puertoAbierto = Test-NetConnection -ComputerName $host_ -Port $puertoDb -WarningAction SilentlyContinue -InformationLevel Quiet
    if (-not $puertoAbierto) {
        Log "Servidor $host_ responde ping pero no el puerto Postgres $puertoDb — se omite sync."
        Escribir-Estado 'omitido' "Puerto $puertoDb cerrado en $host_"
        exit 0
    }

    Log "Servidor $host_ alcanzable — arrancando sync."

    # ─── 1) Dump desde el servidor ────────────────────────────────────────────
    $archivoDump = Join-Path $tmpDir "dump_$(Get-Date -Format 'yyyyMMdd_HHmmss').sql"
    $env:PGPASSWORD = $cfg['SERVIDOR_DB_PASSWORD']

    & $pgDump `
        --host=$host_ `
        --port=$puertoDb `
        --username=$($cfg['SERVIDOR_DB_USUARIO']) `
        --dbname=$($cfg['SERVIDOR_DB_NOMBRE']) `
        --clean --if-exists --no-owner --no-privileges `
        --file=$archivoDump

    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $archivoDump) -or (Get-Item $archivoDump).Length -eq 0) {
        Log "ERROR: pg_dump falló (código $LASTEXITCODE) o generó un archivo vacío."
        Escribir-Estado 'error' "pg_dump falló (código $LASTEXITCODE)"
        Remove-Item $archivoDump -ErrorAction SilentlyContinue
        exit 1
    }
    Log "Dump generado: $archivoDump ($([math]::Round((Get-Item $archivoDump).Length / 1KB, 1)) KB)"

    # ─── 2) Restaurar en la base LOCAL de la notebook ────────────────────────
    $env:PGPASSWORD = $cfg['LOCAL_DB_PASSWORD']

    & $psql `
        --host=localhost `
        --port=$($cfg['LOCAL_DB_PUERTO']) `
        --username=$($cfg['LOCAL_DB_USUARIO']) `
        --dbname=$($cfg['LOCAL_DB_NOMBRE']) `
        --set=ON_ERROR_STOP=1 `
        --quiet `
        --file=$archivoDump `
        *> (Join-Path $tmpDir 'ultimo_restore.log')

    if ($LASTEXITCODE -ne 0) {
        Log "ERROR: la restauración local falló (código $LASTEXITCODE). Ver tmp/ultimo_restore.log"
        Escribir-Estado 'error' "psql (restore) falló (código $LASTEXITCODE)"
        exit 1
    }

    Log "Sync completo — base local actualizada con los datos del servidor."
    Escribir-Estado 'ok' 'Sincronizado correctamente'

    # Conservar solo el último dump para no llenar el disco
    Get-ChildItem $tmpDir -Filter 'dump_*.sql' |
        Sort-Object LastWriteTime -Descending |
        Select-Object -Skip 1 |
        Remove-Item -ErrorAction SilentlyContinue

}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    Remove-Item $lockFile -ErrorAction SilentlyContinue
}

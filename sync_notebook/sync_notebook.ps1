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

    # ─── 2) Recrear la base LOCAL de la notebook desde cero ──────────────────
    # No se restaura encima de la base existente: si el servidor borró una
    # tabla o columna en una migración (como pasó con "tipos_instalacion"
    # el 09/08/2026), esa tabla queda huérfana en la notebook — y la
    # próxima vez que el dump nuevo intente recrear una tabla de la que esa
    # huérfana depende por foreign key (ej. "productos"), el restore se
    # corta a la mitad con "cannot drop constraint ... because other
    # objects depend on it", dejando la base de la notebook a medio
    # actualizar. Recrear la base de cero en cada sync elimina esa clase
    # entera de problema, no solo el de hoy — probado localmente
    # reproduciendo el escenario antes de este cambio.
    $env:PGPASSWORD = $cfg['LOCAL_DB_PASSWORD']
    $dbNombre = $cfg['LOCAL_DB_NOMBRE']

    & $psql `
        --host=localhost --port=$($cfg['LOCAL_DB_PUERTO']) --username=$($cfg['LOCAL_DB_USUARIO']) `
        --dbname=postgres --set=ON_ERROR_STOP=1 --quiet `
        --command="DROP DATABASE IF EXISTS $dbNombre WITH (FORCE);" `
        --command="CREATE DATABASE $dbNombre OWNER $($cfg['LOCAL_DB_USUARIO']);" `
        *> (Join-Path $tmpDir 'ultimo_recreate.log')

    if ($LASTEXITCODE -ne 0) {
        Log "ERROR: no se pudo recrear la base local (código $LASTEXITCODE). Ver tmp/ultimo_recreate.log — probablemente el usuario $($cfg['LOCAL_DB_USUARIO']) no tiene el atributo CREATEDB (ver docs/sync_notebook.md)."
        Escribir-Estado 'error' "Recrear base local falló (código $LASTEXITCODE)"
        exit 1
    }

    # ─── 3) Restaurar el dump en la base recién creada ───────────────────────
    & $psql `
        --host=localhost `
        --port=$($cfg['LOCAL_DB_PUERTO']) `
        --username=$($cfg['LOCAL_DB_USUARIO']) `
        --dbname=$dbNombre `
        --set=ON_ERROR_STOP=1 `
        --quiet `
        --file=$archivoDump `
        *> (Join-Path $tmpDir 'ultimo_restore.log')

    if ($LASTEXITCODE -ne 0) {
        Log "ERROR: la restauración local falló (código $LASTEXITCODE). Ver tmp/ultimo_restore.log"
        Escribir-Estado 'error' "psql (restore) falló (código $LASTEXITCODE)"
        exit 1
    }

    # ─── 4) Fotos de productos ───────────────────────────────────────────────
    # La base guarda solo la RUTA de cada imagen (MEDIA_ROOT = backend/media),
    # no el archivo. Sin este paso la notebook restaura el catálogo entero
    # pero muestra todos los productos con la foto rota, porque los archivos
    # solo existen en la PC servidor.
    #
    # Es opcional a propósito: requiere compartir backend\media en la red
    # (ver docs/sync_notebook.md). Si no está configurado, o si la carpeta
    # compartida no responde, el sync de datos igual se da por bueno — las
    # fotos son secundarias frente al stock y los pedidos.
    #
    # Todo el bloque va dentro de un try propio: llegado acá la base YA quedó
    # sincronizada, así que ningún problema con la carpeta de red (permisos,
    # share caído, disco lleno) debe hacer fracasar un sync que en lo
    # importante salió bien.
    $mediaUnc = $cfg['SERVIDOR_MEDIA_UNC']
    $detalleMedia = 'sin fotos'

    try {
        if (-not $mediaUnc) {
            Log "SERVIDOR_MEDIA_UNC vacío — se omite la copia de fotos (los productos se van a ver sin imagen)."
        }
        elseif (-not (Test-Path $mediaUnc -ErrorAction SilentlyContinue)) {
            Log "ADVERTENCIA: no se pudo acceder a $mediaUnc — se omite la copia de fotos y se conservan las que ya estaban."
        }
        else {
            # Guarda contra un /MIR destructivo: si la carpeta compartida está
            # accesible pero vacía (share mal configurado, disco recién
            # cambiado), espejarla borraría todas las fotos que ya tenía.
            $primerArchivo = Get-ChildItem $mediaUnc -Recurse -File -ErrorAction SilentlyContinue |
                             Select-Object -First 1
            if (-not $primerArchivo) {
                Log "ADVERTENCIA: $mediaUnc está accesible pero vacía — se omite la copia para no borrar las fotos locales."
            }
            else {
                $mediaLocal = Join-Path (Split-Path -Parent $carpeta) 'backend\media'
                if (-not (Test-Path $mediaLocal)) {
                    New-Item -ItemType Directory -Path $mediaLocal -Force | Out-Null
                }

                # /MIR (espejo real) y no /E: acá sí corresponde borrar lo que
                # ya no está en el servidor, porque la notebook es un espejo
                # que se refresca cada 5 minutos y si no las fotos viejas se
                # acumularían para siempre. Mismo criterio que recrear la base.
                & robocopy $mediaUnc $mediaLocal /MIR /NFL /NDL /NJH /NJS /R:1 /W:1 | Out-Null

                # robocopy devuelve 0-7 para resultados normales (0 = sin
                # cambios, 1 = copió, 3 = copió y borró); 8 o más es error.
                if ($LASTEXITCODE -ge 8) {
                    Log "ADVERTENCIA: robocopy falló al copiar las fotos (código $LASTEXITCODE) — la base igual quedó actualizada."
                    $detalleMedia = 'fotos con error'
                }
                else {
                    $cantFotos = (Get-ChildItem $mediaLocal -Recurse -File -ErrorAction SilentlyContinue).Count
                    Log "Fotos sincronizadas: $cantFotos archivos en backend\media."
                    $detalleMedia = "$cantFotos fotos"
                }
                $global:LASTEXITCODE = 0
            }
        }
    }
    catch {
        Log "ADVERTENCIA: falló la copia de fotos ($($_.Exception.Message)) — la base igual quedó actualizada."
        $detalleMedia = 'fotos con error'
    }

    Log "Sync completo — base local actualizada con los datos del servidor."
    Escribir-Estado 'ok' "Sincronizado correctamente ($detalleMedia)"

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

# Instala Ordenito en Windows para tu usuario (no necesita administrador).
# Uso: doble clic en instalar.cmd, o en PowerShell:  .\instalar.cmd
# ORDENITO_SIN_SERVICIO=1 instala sin activar el servicio (útil para pruebas).
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Verde($t) { Write-Host $t -ForegroundColor Green }
function Aviso($t) { Write-Host $t -ForegroundColor Yellow }

# Python 3.9 o más nuevo (el lanzador 'py' primero: no es el atajo de la Microsoft Store)
$python = $null
foreach ($c in @(@('py', '-3'), @('python'))) {
    try {
        $ruta = & $c[0] $c[1..9] -c "import sys; print(sys.executable) if sys.version_info >= (3, 9) else sys.exit(1)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $ruta) { $python = $ruta.Trim(); break }
    } catch {}
}
if (-not $python) {
    Write-Host "Ordenito necesita Python 3.9 o más nuevo."
    Write-Host "Instálalo con:  winget install Python.Python.3.12   (o desde python.org) y vuelve a ejecutar instalar.cmd"
    exit 1
}
$pythonw = Join-Path (Split-Path $python) 'pythonw.exe'
if (-not (Test-Path $pythonw)) { $pythonw = $python }

$destino = Join-Path $env:LOCALAPPDATA 'Programs\Ordenito'
$bin = Join-Path $destino 'bin'
New-Item -ItemType Directory -Force $bin | Out-Null
Copy-Item ordenito.py, ordenito_app.py, ordenito.png -Destination $destino -Force
Set-Content -Encoding ascii (Join-Path $bin 'ordenito.cmd') "@`"$python`" -I `"$destino\ordenito.py`" %*"
Set-Content -Encoding ascii (Join-Path $bin 'ordenito-app.cmd') "@start `"`" `"$pythonw`" -I `"$destino\ordenito_app.py`" %*"
Verde "✓ Programa:  $destino"

# El comando 'ordenito' en cualquier terminal nueva
$path = [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not $path) { $path = '' }
if (($path -split ';') -notcontains $bin) {
    [Environment]::SetEnvironmentVariable('Path', ($path.TrimEnd(';') + ";$bin").TrimStart(';'), 'User')
    Verde "✓ Comando:   'ordenito' (abre una terminal nueva para usarlo)"
}

# Nombre e ícono de Ordenito en las notificaciones de Windows
$clave = 'HKCU:\Software\Classes\AppUserModelId\Gr8coolmind.Ordenito'
New-Item -Force $clave | Out-Null
Set-ItemProperty $clave DisplayName 'Ordenito'
Set-ItemProperty $clave IconUri (Join-Path $destino 'ordenito.png')

# La app en el menú Inicio
$tk = & $python -c "import tkinter" 2>$null; $hayTk = ($LASTEXITCODE -eq 0)
if ($hayTk) {
    $acceso = Join-Path ([Environment]::GetFolderPath('Programs')) 'Ordenito.lnk'
    $sc = (New-Object -ComObject WScript.Shell).CreateShortcut($acceso)
    $sc.TargetPath = $pythonw
    $sc.Arguments = "-I `"$destino\ordenito_app.py`""
    $sc.WorkingDirectory = $destino
    $sc.Description = 'Ordena tus descargas solas'
    $sc.Save()
    Verde "✓ App:       búscala como 'Ordenito' en el menú Inicio"
} else {
    Aviso "· La app con ventana necesita Tkinter: reinstala Python marcando 'tcl/tk and IDLE'."
    Aviso "  El servicio automático y el comando 'ordenito' funcionan igual sin ella."
}

# Reglas de ejemplo (si ya tienes las tuyas, no se tocan)
$conf = Join-Path $env:APPDATA 'ordenito\reglas.conf'
if (Test-Path $conf) {
    Verde "✓ Reglas:    $conf (ya existían, no se tocan)"
} else {
    New-Item -ItemType Directory -Force (Split-Path $conf) | Out-Null
    Copy-Item reglas.ejemplo.conf $conf
    Verde "✓ Reglas:    $conf (ejemplo, edítalas a tu gusto)"
}

if ($env:ORDENITO_SIN_SERVICIO) {
    Aviso "· Servicio no activado (ORDENITO_SIN_SERVICIO)."
} else {
    & $python -I "$destino\ordenito.py" servicio encender
    if ($LASTEXITCODE -ne 0) { Aviso "· No pude encender el servicio: prueba 'ordenito servicio encender'." }
}

Write-Host @"

Listo. Todo lo que descargues se ordenará solo.
  ordenito-app                abre la ventana de Ordenito
  ordenito simular            qué haría ahora mismo
  ordenito explicar ARCHIVO   por qué un archivo va a donde va
  ordenito deshacer           devuelve el último archivo movido
"@

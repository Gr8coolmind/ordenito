# Quita Ordenito de Windows. Tus reglas y el historial se conservan salvo que pases -todo.
param([switch]$todo)
$destino = Join-Path $env:LOCALAPPDATA 'Programs\Ordenito'
$bin = Join-Path $destino 'bin'

if (Test-Path "$destino\ordenito.py") {
    $python = (Get-Content "$bin\ordenito.cmd" -ErrorAction SilentlyContinue) -replace '^@"([^"]+)".*', '$1'
    if ($python -and (Test-Path $python)) { & $python -I "$destino\ordenito.py" servicio apagar | Out-Null }
}
Remove-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name Ordenito -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $destino -ErrorAction SilentlyContinue
Remove-Item -Force (Join-Path ([Environment]::GetFolderPath('Programs')) 'Ordenito.lnk') -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force 'HKCU:\Software\Classes\AppUserModelId\Gr8coolmind.Ordenito' -ErrorAction SilentlyContinue
$path = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($path) {
    [Environment]::SetEnvironmentVariable('Path', (($path -split ';') | Where-Object { $_ -and $_ -ne $bin }) -join ';', 'User')
}

if ($todo) {
    Remove-Item -Recurse -Force (Join-Path $env:APPDATA 'ordenito'), (Join-Path $env:LOCALAPPDATA 'ordenito') -ErrorAction SilentlyContinue
    Write-Host "Ordenito desinstalado, junto con tus reglas e historial."
} else {
    Write-Host "Ordenito desinstalado. Tus reglas siguen en $env:APPDATA\ordenito (bórralas con -todo)."
}
Write-Host "Tus archivos no se tocan: quedan donde Ordenito los dejó."

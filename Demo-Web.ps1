#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('Rutas','Preparar','Inspeccionar','Iniciar','Comprobar','Pruebas')]
    [string]$Accion = 'Rutas',
    [string]$Directorio = 'D:\Projects\ServerTec\demo-web-20261019',
    [string]$Direccion = '127.0.0.1',
    [ValidateSet('learngraphicsprogramming.dynamics','servertec-demo.example.invalid')]
    [string]$Nombre = 'learngraphicsprogramming.dynamics',
    [ValidateRange(1,65535)][int]$Puerto = 443,
    [switch]$AutoridadDesechable,
    [switch]$ExposicionAutorizada
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$demoPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if ($Accion -eq 'Rutas') {
    Write-Output ('Codigo: ' + $PSScriptRoot)
    Write-Output ('Material demo separado: ' + $Directorio)
    Write-Output ('URL seleccionada: https://' + $Nombre + '/')
    Write-Output 'No abre datos reales, puertos, hosts, firewall ni almacenes de confianza.'
    return
}
if (-not (Test-Path -LiteralPath $demoPython)) {
    throw 'Falta el entorno local .venv con las dependencias existentes. No se instala nada automaticamente.'
}
$demoArgs = @()
switch ($Accion) {
    'Preparar' {
        $demoArgs = @('demo_pki.py','prepare','--directory',$Directorio,'--hostname',$Nombre)
        if ($AutoridadDesechable) { $demoArgs += '--one-shot' }
    }
    'Inspeccionar' { $demoArgs = @('demo_pki.py','inspect','--directory',$Directorio,'--hostname',$Nombre) }
    'Iniciar' {
        $demoAddress = [System.Net.IPAddress]::Parse($Direccion)
        if (-not [System.Net.IPAddress]::IsLoopback($demoAddress) -and -not $ExposicionAutorizada) {
            throw 'La escucha de red necesita autorizacion previa concreta; despues usar -ExposicionAutorizada. No cambia firewall/router.'
        }
        # Rechazar nombre distinto o certificado caducado antes de iniciar.
        & $demoPython (Join-Path $PSScriptRoot 'demo_pki.py') 'inspect' '--directory' $Directorio '--hostname' $Nombre | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'La identidad de demo no es valida para el nombre seleccionado.' }
        Write-Output 'Demo en primer plano. Ctrl+C detiene solo esta ejecucion. No cerrar procesos por nombre o puerto.'
        $demoArgs = @('demo_web.py','serve','--enable-demo','--hostname',$Nombre,'--host',$Direccion,'--port',([string]$Puerto),
                      '--cert',(Join-Path $Directorio 'runtime\server.pem'),
                      '--key',(Join-Path $Directorio 'runtime\server-key.pem'))
    }
    'Comprobar' { $demoArgs = @('demo_check.py','--directory',$Directorio,'--hostname',$Nombre,'--address',$Direccion,'--port',([string]$Puerto)) }
    'Pruebas' {
        $demoArgs = @('-X','dev','-m','pytest','test_demo_web.py','test_demo_pki.py','test_demo_check.py','test_demo_dynv6.py','test_demo_public_probe.py',
                      '-q','-p','no:cacheprovider','-W','error::ResourceWarning',
                      '-W','error::pytest.PytestUnraisableExceptionWarning')
    }
}
Push-Location -LiteralPath $PSScriptRoot
try {
    & $demoPython @demoArgs
    if ($LASTEXITCODE -ne 0) { throw ('Fallo demo; codigo ' + $LASTEXITCODE) }
} finally { Pop-Location }

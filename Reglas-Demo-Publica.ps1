#requires -Version 5.1
# Firewall exclusivo para la demo HTTPS. No modifica router, procesos ni datos.
[CmdletBinding()]
param([ValidateSet('Plan','Aplicar','Verificar','Retirar')][string]$Accion='Plan')
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest

$alias='Ethernet 2'
$programa=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$grupo='ServerTec-Demo443-20261019'
$items=@(
    [pscustomobject]@{Name='ServerTec-Demo443-v4-20261019'; Family='IPv4'; IP='198.51.100.10'},
    [pscustomobject]@{Name='ServerTec-Demo443-v6-20261019'; Family='IPv6'; IP='2001:db8:feed::10'}
)

function Get-OurRule($name) {
    $rules=@(Get-NetFirewallRule -PolicyStore PersistentStore -Name $name -ErrorAction SilentlyContinue)
    if ($rules.Count -gt 1) { throw 'Nombre de regla ambiguo; no se modifica nada.' }
    if ($rules.Count -eq 0) { return $null }
    return $rules[0]
}

function Assert-OurRule($rule,$item) {
    if ($null -eq $rule) { throw 'La regla esperada no existe.' }
    $port=Get-NetFirewallPortFilter -AssociatedNetFirewallRule $rule
    $addr=Get-NetFirewallAddressFilter -AssociatedNetFirewallRule $rule
    $app=Get-NetFirewallApplicationFilter -AssociatedNetFirewallRule $rule
    $iface=Get-NetFirewallInterfaceFilter -AssociatedNetFirewallRule $rule
    $addresses=@($addr.LocalAddress)
    $parsed=$null
    $matchesIP=($addresses.Count -eq 1 -and
        [Net.IPAddress]::TryParse([string]$addresses[0],[ref]$parsed) -and
        $parsed.Equals([Net.IPAddress]::Parse($item.IP)))
    if (-not (
        [string]$rule.Name -eq $item.Name -and
        [string]$rule.Group -eq $grupo -and
        [string]$rule.Enabled -eq 'True' -and
        [string]$rule.Action -eq 'Allow' -and
        [string]$rule.Direction -eq 'Inbound' -and
        [string]$rule.Profile -eq 'Public' -and
        [string]$rule.EdgeTraversalPolicy -eq 'Block' -and
        [string]$port.Protocol -in @('TCP','6') -and
        (@($port.LocalPort) -join ',') -eq '443' -and
        (@($port.RemotePort) -join ',') -eq 'Any' -and
        $matchesIP -and
        (@($addr.RemoteAddress) -join ',') -eq 'Any' -and
        [string]$app.Program -eq $programa -and
        (@($iface.InterfaceAlias) -join ',') -eq $alias
    )) { throw ('La regla ha cambiado o no nos pertenece: ' + $item.Name) }
}

function Assert-Environment {
    if (-not (Test-Path -LiteralPath $programa -PathType Leaf)) {
        throw 'Falta Python local de .venv. No aplicar.'
    }
    $nic=@(Get-NetAdapter -Name $alias -ErrorAction Stop)
    $network=@(Get-NetConnectionProfile -InterfaceAlias $alias -ErrorAction Stop)
    $fw=@(Get-NetFirewallProfile -PolicyStore ActiveStore -Name Public -ErrorAction Stop)
    if ($nic.Count -ne 1 -or [string]$nic[0].Status -ne 'Up' -or
        $network.Count -ne 1 -or [string]$network[0].NetworkCategory -ne 'Public' -or
        $fw.Count -ne 1 -or [string]$fw[0].Enabled -ne 'True' -or
        [string]$fw[0].DefaultInboundAction -ne 'Block') {
        throw 'La interfaz o firewall no coinciden con el diagnostico autorizado.'
    }
    foreach ($item in $items) {
        $ip=@(Get-NetIPAddress -InterfaceAlias $alias -AddressFamily $item.Family -ErrorAction Stop |
            Where-Object { $_.IPAddress -eq $item.IP -and [string]$_.AddressState -eq 'Preferred' })
        if ($ip.Count -ne 1) { throw ('IP ya no asignada: ' + $item.IP) }
        if ($item.Family -eq 'IPv6' -and [string]$ip[0].SuffixOrigin -eq 'Random') {
            throw 'Se detecto IPv6 temporal. No aplicar.'
        }
    }
}

if ($Accion -eq 'Plan') {
    [pscustomobject]@{
        Programa=$programa; Interfaz=$alias; Perfil='Public'; Puerto='TCP 443'
        Origen='Any (publico general)'; IPv4=$items[0].IP; IPv6=$items[1].IP
        Efecto='Solo nuevas reglas de Windows; sin NAT/ACL router, sin servidores y sin datos'
    } | ConvertTo-Json
    Assert-Environment
    Write-Output 'Plan revisado, NINGUN cambio aplicado.'
    return
}

if ($Accion -eq 'Verificar') {
    foreach ($item in $items) {
        $rule=Get-OurRule $item.Name
        if ($null -eq $rule) { Write-Output ('Ausente: '+$item.Name) }
        else { Assert-OurRule $rule $item; Write-Output ('Valida: '+$item.Name) }
    }
    return
}

$id=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal($id)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Necesitas PowerShell como administrador para Aplicar o Retirar.'
}

if ($Accion -eq 'Retirar') {
    # Verificar ambas antes de borrar alguna.
    foreach ($item in $items) {
        $r=Get-OurRule $item.Name
        if ($null -ne $r) { Assert-OurRule $r $item }
    }
    foreach ($item in $items) {
        if ($null -ne (Get-OurRule $item.Name)) {
            Remove-NetFirewallRule -PolicyStore PersistentStore -Name $item.Name -ErrorAction Stop
            Write-Output ('Retirada: '+$item.Name)
        }
    }
    Write-Output 'El router y los procesos no se modificaron.'
    return
}

Assert-Environment
foreach ($item in $items) {
    if ($null -ne (Get-OurRule $item.Name) -or
        @(Get-NetFirewallRule -PolicyStore ActiveStore -Name $item.Name -ErrorAction SilentlyContinue).Count -gt 0) {
        throw ('La regla ya existe; no se sobrescribe: '+$item.Name)
    }
}

$created=New-Object 'System.Collections.Generic.List[object]'
try {
    foreach ($item in $items) {
        $parameters=@{
            PolicyStore='PersistentStore'; Name=$item.Name
            DisplayName=('ServerTec demo TCP 443 '+$item.Family)
            Group=$grupo; Description='SOLO menu publico de demo'
            Enabled='True'; Direction='Inbound'; Action='Allow'
            Protocol='TCP'; LocalPort=443; RemotePort='Any'
            LocalAddress=$item.IP; RemoteAddress='Any'
            Program=$programa; InterfaceAlias=$alias
            Profile='Public'; EdgeTraversalPolicy='Block'
        }
        New-NetFirewallRule @parameters -ErrorAction Stop | Out-Null
        $created.Add($item)
        Assert-OurRule (Get-OurRule $item.Name) $item
        Write-Output ('Aplicada: '+$item.Name)
    }
} catch {
    foreach ($item in $created) {
        try {
            $r=Get-OurRule $item.Name
            if ($null -ne $r) {
                Assert-OurRule $r $item
                Remove-NetFirewallRule -PolicyStore PersistentStore -Name $item.Name -ErrorAction Stop
            }
        } catch {
            Write-Warning ('Revisar regla parcial: '+$item.Name)
        }
    }
    throw 'Fallo en reglas de demo. Se intento revertir lo nuevo; revisa Verificar.'
}
Write-Output 'Dos reglas de firewall listas. No se configuro el router ni se iniciaron servidores.'

#requires -Version 5.1
<#
Diagnostico y borrador de exposicion: SOLO LECTURA.
No aplica reglas, no abre conexiones, no consulta servicios externos, no eleva,
no escribe archivos y no detiene procesos. El resultado no prueba acceso externo.
En IPv4, DireccionServidor es la IP LOCAL; DireccionWAN es la IP del router.
Las direcciones del cliente y de WAN son datos aportados, no verificados aqui.
#>
[CmdletBinding()]
param(
    [string]$DireccionServidor,
    [string]$DireccionCliente,
    [string]$DireccionWAN,
    [switch]$AccesoGeneral
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Read-LiteralAddress([string]$Value, [string]$Label) {
    $parsed = $null
    if ($Value -match '[/%\s]' -or -not [Net.IPAddress]::TryParse($Value, [ref]$parsed)) {
        throw ($Label + ': se requiere una IP literal sin prefijo, zona ni nombre DNS.')
    }
    # Evitar formatos IPv4 abreviados, octales o enteros admitidos por .NET.
    if ($parsed.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork -and
        $Value -ne $parsed.ToString()) {
        throw ($Label + ': usar los cuatro octetos IPv4 decimales canonicos.')
    }
    return $parsed
}

function Test-InPrefix([Net.IPAddress]$Address, [string]$Prefix) {
    $parts = $Prefix.Split('/')
    $network = [Net.IPAddress]::Parse($parts[0])
    if ($Address.AddressFamily -ne $network.AddressFamily) { return $false }
    $bits = [int]$parts[1]
    $left = $Address.GetAddressBytes()
    $right = $network.GetAddressBytes()
    for ($index = 0; $index -lt $left.Length -and $bits -gt 0; $index++) {
        $width = [Math]::Min(8, $bits)
        $mask = (255 -shl (8 - $width)) -band 255
        if (($left[$index] -band $mask) -ne ($right[$index] -band $mask)) { return $false }
        $bits -= $width
    }
    return $true
}

function Test-GlobalCandidate([Net.IPAddress]$Address) {
    # Clasificacion conservadora; no demuestra asignacion, propiedad o ruta.
    if ($Address.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork) {
        foreach ($prefix in @('0.0.0.0/8','10.0.0.0/8','100.64.0.0/10',
            '127.0.0.0/8','169.254.0.0/16','172.16.0.0/12','192.0.0.0/24',
            '192.0.2.0/24','192.88.99.0/24','192.168.0.0/16','198.18.0.0/15',
            '198.51.100.0/24','203.0.113.0/24','224.0.0.0/4','240.0.0.0/4')) {
            if (Test-InPrefix $Address $prefix) { return $false }
        }
        return $true
    }
    if (-not (Test-InPrefix $Address '2000::/3')) { return $false }
    foreach ($prefix in @('2001::/23','2001:db8::/32','2002::/16','3ffe::/16','3fff::/20')) {
        if (Test-InPrefix $Address $prefix) { return $false }
    }
    return $true
}

function Test-PrivateV4([Net.IPAddress]$Address) {
    foreach ($prefix in @('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')) {
        if (Test-InPrefix $Address $prefix) { return $true }
    }
    return $false
}

function Test-Port443($Ports) {
    foreach ($port in @($Ports)) {
        if ([string]$port -in @('Any','443')) { return $true }
        if ([string]$port -match '^(\d+)-(\d+)$') {
            if ([int]$Matches[1] -le 443 -and [int]$Matches[2] -ge 443) { return $true }
        } elseif ([string]$port -notmatch '^\d+$') {
            # Un token dinamico no se resuelve mediante conjeturas.
            return $true
        }
    }
    return $false
}

function Get-FilterMap($Filters) {
    $result = @{}
    foreach ($filter in @($Filters)) { $result[[string]$filter.InstanceID] = $filter }
    return $result
}

function Get-AddressMatch($Filters, [Net.IPAddress]$Address) {
    if ($null -eq $Address) { return 'Indeterminado' }
    $unknown = $false
    foreach ($filter in @($Filters)) {
        $value = [string]$filter
        if ($value -eq 'Any') { return 'Coincide' }
        $literal = $null
        if ([Net.IPAddress]::TryParse($value, [ref]$literal)) {
            if ($literal.Equals($Address)) { return 'Coincide' }
        } elseif ($value -match '^([^/]+)/([0-9]+)$') {
            try {
                $prefixAddress = [Net.IPAddress]::Parse($Matches[1])
                $prefixBits = [int]$Matches[2]
                $maxBits = 128
                if ($prefixAddress.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork) { $maxBits = 32 }
                if ($prefixBits -gt $maxBits) { $unknown = $true }
                elseif (Test-InPrefix $Address $value) { return 'Coincide' }
            } catch { $unknown = $true }
        } else {
            # Rangos, Internet, LocalSubnet y otros tokens requieren evaluacion adicional.
            $unknown = $true
        }
    }
    if ($unknown) { return 'Indeterminado' }
    return 'NoCoincide'
}

$server = $null
$client = $null
$wan = $null
if ($DireccionServidor) { $server = Read-LiteralAddress $DireccionServidor 'DireccionServidor' }
if ($DireccionCliente) {
    $client = Read-LiteralAddress $DireccionCliente 'DireccionCliente'
    if (-not (Test-GlobalCandidate $client)) { throw 'DireccionCliente no es una candidata publica global permitida; no usar IP privada, CGNAT, local o reservada.' }
}
if ($DireccionWAN) {
    $wan = Read-LiteralAddress $DireccionWAN 'DireccionWAN'
    if ($wan.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or -not (Test-GlobalCandidate $wan)) {
        throw 'DireccionWAN requiere una IPv4 publica global candidata, leida en el router; una WAN privada o CGNAT no sirve para este plan.'
    }
}
if ($null -ne $server) {
    if ($server.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetworkV6) {
        if (-not (Test-GlobalCandidate $server)) { throw 'El servidor IPv6 requiere una direccion global candidata, no loopback, local o reservada.' }
    } elseif (-not (Test-GlobalCandidate $server) -and -not (Test-PrivateV4 $server)) {
        throw 'El servidor IPv4 debe ser una direccion local publica candidata o privada RFC1918; no loopback, CGNAT o enlace local.'
    }
}
if ($null -ne $server -and $null -ne $client) {
    if ($server.AddressFamily -ne $client.AddressFamily) { throw 'Servidor y cliente deben usar la misma familia IP.' }
    if ($server.Equals($client) -or ($null -ne $wan -and $wan.Equals($client))) { throw 'La direccion del cliente debe proceder de OTRA RED, distinta de la PC y de su WAN.' }
}

$warnings = New-Object 'System.Collections.Generic.List[string]'
$pending = New-Object 'System.Collections.Generic.List[string]'
$blocks = New-Object 'System.Collections.Generic.List[string]'
$addresses = @(Get-NetIPAddress | Select-Object InterfaceIndex,InterfaceAlias,IPAddress,PrefixLength,
    @{Name='AddressFamily';Expression={$_.AddressFamily.ToString()}},
    @{Name='AddressState';Expression={$_.AddressState.ToString()}},
    @{Name='SuffixOrigin';Expression={$_.SuffixOrigin.ToString()}},SkipAsSource)
$interfaces = @(Get-NetAdapter | Select-Object InterfaceIndex,Name,
    @{Name='Status';Expression={$_.Status.ToString()}})
$routes = @(Get-NetRoute -DestinationPrefix '0.0.0.0/0','::/0' | Select-Object InterfaceIndex,InterfaceAlias,DestinationPrefix,NextHop,RouteMetric)
$profiles = @(Get-NetConnectionProfile | Select-Object InterfaceIndex,InterfaceAlias,
    @{Name='NetworkCategory';Expression={$_.NetworkCategory.ToString()}},
    @{Name='IPv4Connectivity';Expression={$_.IPv4Connectivity.ToString()}},
    @{Name='IPv6Connectivity';Expression={$_.IPv6Connectivity.ToString()}})
$firewallProfiles = @()
try {
    $firewallProfiles = @(Get-NetFirewallProfile -PolicyStore ActiveStore | Select-Object Name,
        @{Name='Enabled';Expression={$_.Enabled.ToString()}},
        @{Name='DefaultInboundAction';Expression={$_.DefaultInboundAction.ToString()}},
        @{Name='AllowInboundRules';Expression={$_.AllowInboundRules.ToString()}},
        @{Name='AllowLocalFirewallRules';Expression={$_.AllowLocalFirewallRules.ToString()}})
} catch { $warnings.Add('No se pudo leer el perfil efectivo de firewall: ' + $_.Exception.Message) }

$venvExecutable = $null
$venvConfig = Join-Path $PSScriptRoot '.venv\pyvenv.cfg'
if (Test-Path -LiteralPath $venvConfig -PathType Leaf) {
    foreach ($line in Get-Content -LiteralPath $venvConfig) {
        # No leer ni publicar el campo command; solo metadata del interprete.
        if ($line -match '^executable\s*=\s*(.+)$') { $venvExecutable = $Matches[1].Trim() }
    }
}
if ($venvExecutable -and -not (Test-Path -LiteralPath $venvExecutable -PathType Leaf)) {
    $warnings.Add('El ejecutable declarado en pyvenv.cfg ya no existe.')
    $venvExecutable = $null
}
$listeners = @()
$rawListeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object LocalPort -eq 443)
foreach ($listener in $rawListeners) {
    $processInfo = $null
    try { $processInfo = Get-CimInstance Win32_Process -Filter ('ProcessId=' + [int]$listener.OwningProcess) }
    catch { $warnings.Add('No se pudo leer metadata del PID ' + [string]$listener.OwningProcess) }
    $processPath = $null
    $processName = $null
    if ($null -ne $processInfo) { $processPath = $processInfo.ExecutablePath; $processName = $processInfo.Name }
    $listeners += [pscustomobject]@{
        LocalAddress = [string]$listener.LocalAddress
        LocalPort = 443
        OwningProcess = [int]$listener.OwningProcess
        ProcessName = $processName
        ExecutablePath = $processPath
        MatchesVenvExecutable = [bool]($venvExecutable -and $processPath -and $processPath -eq $venvExecutable)
    }
}
$pythonSockets = @($listeners | Where-Object MatchesVenvExecutable)
$program = $venvExecutable
$programEvidence = 'Metadata de .venv; confirmar el ejecutable que posea el nuevo socket.'
if ($pythonSockets.Count -gt 0) {
    $program = $pythonSockets[0].ExecutablePath
    $programEvidence = 'Metadata de .venv coincide con ejecutable de listener443. No prueba por si sola que sea la demo.'
}

$selectedAddress = $null
$selectedProfile = $null
$profileName = $null
if ($null -ne $server) {
    $matchingAddresses = @($addresses | Where-Object {
        $candidate = [Net.IPAddress]::Parse($_.IPAddress)
        $candidate.Equals($server)
    })
    if ($matchingAddresses.Count -ne 1) { throw 'DireccionServidor no identifica una unica IP actualmente asignada a esta PC.' }
    $selectedAddress = $matchingAddresses[0]
    if ($selectedAddress.AddressState -ne 'Preferred') { $blocks.Add('La direccion local no esta en estado Preferred.') }
    if ($selectedAddress.SuffixOrigin -eq 'Random') { $warnings.Add('La direccion seleccionada es temporal; puede cambiar y requerir nuevo plan.') }
    $matchingProfiles = @($profiles | Where-Object InterfaceIndex -eq $selectedAddress.InterfaceIndex)
    if ($matchingProfiles.Count -eq 1) {
        $selectedProfile = $matchingProfiles[0]
        $profileName = $selectedProfile.NetworkCategory
        if ($profileName -eq 'DomainAuthenticated') { $profileName = 'Domain' }
    } else { $blocks.Add('No se identifico un unico perfil Windows para la interfaz seleccionada.') }
    $prefix = '::/0'
    if ($server.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork) { $prefix = '0.0.0.0/0' }
    if (@($routes | Where-Object { $_.InterfaceIndex -eq $selectedAddress.InterfaceIndex -and $_.DestinationPrefix -eq $prefix }).Count -eq 0) {
        $blocks.Add('No hay ruta por defecto de esa familia en la interfaz seleccionada.')
    }
    foreach ($existingListener in $listeners) {
        if ($existingListener.LocalAddress -eq $server.ToString() -or
            $existingListener.LocalAddress -eq '::' -or
            ($prefix -eq '0.0.0.0/0' -and $existingListener.LocalAddress -eq '0.0.0.0')) {
            $blocks.Add('Un listener443 ocupa la direccion solicitada o un comodin potencialmente incompatible. No se detuvo.')
        }
    }
}

$firewallCandidates = @()
$firewallReadComplete = $false
try {
    $rules = @(Get-NetFirewallRule -PolicyStore ActiveStore -Enabled True -Direction Inbound -Action Allow)
    $ports = Get-FilterMap @($rules | Get-NetFirewallPortFilter)
    $apps = Get-FilterMap @($rules | Get-NetFirewallApplicationFilter)
    $scopes = Get-FilterMap @($rules | Get-NetFirewallAddressFilter)
    $ifaces = Get-FilterMap @($rules | Get-NetFirewallInterfaceFilter)
    $services = Get-FilterMap @($rules | Get-NetFirewallServiceFilter)
    $filtersMissing = $false
    foreach ($rule in $rules) {
        $key = [string]$rule.InstanceID
        if (-not $ports.ContainsKey($key) -or -not $apps.ContainsKey($key) -or
            -not $scopes.ContainsKey($key) -or -not $ifaces.ContainsKey($key) -or -not $services.ContainsKey($key)) {
            $warnings.Add('Faltan filtros de una regla efectiva; la evaluacion del firewall queda incompleta.')
            $filtersMissing = $true
            continue
        }
        $portFilter = $ports[$key]
        if ([string]$portFilter.Protocol -notin @('TCP','Any','6','256')) { continue }
        if (-not (Test-Port443 $portFilter.LocalPort)) { continue }
        $appFilter = $apps[$key]
        $programFilter = [Environment]::ExpandEnvironmentVariables([string]$appFilter.Program)
        if ($program -and $programFilter -notin @('Any','*','') -and $programFilter -ne $program) { continue }
        if ($appFilter.Package) { continue }
        $ruleProfiles = [string]$rule.Profile
        if ($profileName -and $ruleProfiles -ne 'Any' -and $ruleProfiles -notmatch ('\b' + [regex]::Escape($profileName) + '\b')) { continue }
        $scopeFilter = $scopes[$key]
        $localMatch = Get-AddressMatch $scopeFilter.LocalAddress $server
        $remoteMatch = Get-AddressMatch $scopeFilter.RemoteAddress $client
        if ($localMatch -eq 'NoCoincide' -or $remoteMatch -eq 'NoCoincide') { continue }
        $interfaceFilter = $ifaces[$key]
        if ($null -ne $selectedAddress -and 'Any' -notin @($interfaceFilter.InterfaceAlias) -and
            $selectedAddress.InterfaceAlias -notin @($interfaceFilter.InterfaceAlias)) { continue }
        $serviceFilter = $services[$key]
        $firewallCandidates += [pscustomobject]@{
            Name = [string]$rule.Name
            Profile = $ruleProfiles
            PolicyStoreSourceType = [string]$rule.PolicyStoreSourceType
            Program = $programFilter
            Protocol = [string]$portFilter.Protocol
            LocalPort = @($portFilter.LocalPort)
            LocalAddress = @($scopeFilter.LocalAddress)
            RemoteAddress = @($scopeFilter.RemoteAddress)
            InterfaceAlias = @($interfaceFilter.InterfaceAlias)
            Service = [string]$serviceFilter.Service
            LocalMatch = $localMatch
            RemoteMatch = $remoteMatch
            BroadRemoteAddress = [bool]('Any' -in @($scopeFilter.RemoteAddress))
            Assessment = 'Candidata; puede estar limitada a una app, usuario o capacidad Windows. No prueba permiso efectivo para Python. Requiere revision adicional; no modificar esta regla.'
        }
    }
    $firewallReadComplete = -not $filtersMissing
} catch { $warnings.Add('No se pudo completar la lectura de reglas/filtros efectivos: ' + $_.Exception.Message) }
if ($firewallCandidates.Count -gt 0) {
    $blocks.Add('Hay Allow candidatas cuya pertenencia a app/usuario/capacidad no se resolvio. No acreditan apertura para Python. Revisar sin borrarlas; una nueva regla estrecha no restringe otra Allow amplia efectiva.')
}
if (-not $firewallReadComplete) { $blocks.Add('La lectura efectiva del firewall no se completo; no preparar aplicacion.') }
if ($profileName) {
    $effectiveProfile = @($firewallProfiles | Where-Object Name -eq $profileName)
    if ($effectiveProfile.Count -ne 1 -or $effectiveProfile[0].Enabled -ne 'True' -or
        $effectiveProfile[0].DefaultInboundAction -ne 'Block') {
        $blocks.Add('No se confirmo firewall activo con entrada predeterminada Block en el perfil seleccionado.')
    }
    if ($effectiveProfile.Count -eq 1 -and ($effectiveProfile[0].AllowInboundRules -eq 'False' -or $effectiveProfile[0].AllowLocalFirewallRules -eq 'False')) {
        $blocks.Add('La politica efectiva no acepta reglas entrantes o locales; no cambiar politica.')
    }
}

$plan = $null
if ($null -eq $server) { $pending.Add('DireccionServidor: IP local concreta y vigente de la interfaz elegida.') }
if ($null -eq $client -and -not $AccesoGeneral) { $pending.Add('Para plan restringido opcional: DireccionCliente publica de la otra red. Para revisar acceso general: -AccesoGeneral, solo plan sin aplicar.') }
if ($null -ne $server -and $server.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork -and $null -eq $wan) {
    $pending.Add('DireccionWAN: IPv4 publica global leida en Internet/WAN del router; confirmar ausencia de CGNAT impeditivo.')
}
$pending.Add('Modelo/router y capacidad de autorizar exclusivamente TCP443 hacia la IP exacta de la PC; estado WAN/CGNAT y ACL no leidos aqui.')
if (-not $AccesoGeneral) { $pending.Add('Si se elige restriccion opcional: confirmar origen del cliente actual. En IPv4 una salida compartida abarca otros usuarios de esa IP.') }
$pending.Add('Mostrar cambios concretos y obtener autorizacion antes de listener de red, firewall/router, hosts o confianza.')
$pending.Add('Resolucion del nombre privado y confianza del cliente Windows/Android, con prueba real posterior en Chrome.')
$pending.Add('El nombre privado y la CA propia requieren configurar cada cliente; este plan de red no permite acceso Chrome de cualquier usuario sin preparacion.')
if ($null -ne $server -and ($null -ne $client -or $AccesoGeneral) -and $selectedAddress -and $profileName -and $program -and
    ($server.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetworkV6 -or $null -ne $wan)) {
    $family = 'v6'
    $sourcePrefix = '/128'
    $publicDestination = $server.ToString()
    $routerAction = 'Permiso de entrada IPv6 TCP443 a la IPv6 exacta de la PC, limitado al origen indicado. No NAT.'
    if ($server.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork) {
        $family = 'v4'; $sourcePrefix = '/32'; $publicDestination = $wan.ToString()
        $routerAction = 'NAT TCP443 externo a la IPv4 local:443, con ACL de origen puntual. Confirmar WAN enrutable y ausencia de CGNAT impeditivo.'
    }
    $remoteAddress = 'Any'
    $clientEvidence = 'AccesoGeneral solicitado SOLO COMO PLAN: todas las IP de Internet pueden intentar TCP443; no identifica clientes ni aplica cambios.'
    if (-not $AccesoGeneral) {
        $remoteAddress = $client.ToString()+$sourcePrefix
        $clientEvidence = 'Aportada por el operador; sin comprobacion externa ni conexion a esa IP.'
    } else {
        $routerAction = 'Permitir exclusivamente TCP443 desde todas las IP de Internet hacia la IP exacta de la PC:443; para IPv4 requiere NAT y WAN enrutable, para IPv6 ACL de entrada. Ningun puerto adicional.'
        $warnings.Add('AccesoGeneral produce un borrador con RemoteAddress=Any: todas las IP de Internet. Requiere autorizacion explicita antes de aplicar; aqui no se aplica.')
    }
    $ruleName = 'ServerTec-Demo-Web-' + (Get-Date).ToUniversalTime().ToString('yyyyMMdd') + '-' + $family
    if ($AccesoGeneral) { $ruleName += '-general' }
    if (Get-NetFirewallRule -PolicyStore ActiveStore -Name $ruleName -ErrorAction SilentlyContinue) {
        $blocks.Add('Ya existe el nombre de regla propuesto; no sobrescribir ni retirar una regla previa.')
    }
    $plan = [pscustomobject]@{
        Status = 'BORRADOR SIN AUTORIZAR; no aplicado'
        ReadyToApply = $false
        PendingExplicitApproval = $true
        GeneralInternetAccessPlan = [bool]$AccesoGeneral
        Hostname = 'learngraphicsprogramming.dynamics'
        ExactUrl = 'https://learngraphicsprogramming.dynamics/'
        PublicDestination = $publicDestination
        ClientAddressEvidence = $clientEvidence
        Listener = [pscustomobject]@{ LocalAddress=$server.ToString(); LocalPort=443; Program=$program; ProgramEvidence=$programEvidence }
        WindowsRule = [pscustomobject]@{
            Name=$ruleName; DisplayName='ServerTec demo web temporal'; Direction='Inbound'; Action='Allow'
            Protocol='TCP'; LocalPort=443; LocalAddress=$server.ToString(); RemoteAddress=$remoteAddress
            Profile=$profileName; InterfaceAlias=$selectedAddress.InterfaceAlias; Program=$program; EdgeTraversalPolicy='Block'
        }
        Router = [pscustomobject]@{ Action=$routerAction; PublicDestination=$publicDestination; ExternalPort=443; LocalDestination=$server.ToString(); LocalPort=443; Source=$remoteAddress }
        ManualApplication = 'Tras autorizacion concreta: usuario aplica la regla nueva en PowerShell elevado y la ACL/NAT exacta en el router. Este script no contiene accion Aplicar.'
        Reversal = 'Conservar identidad y filtros de lo creado. Retirar solo esa regla y ACL/NAT nuevas si siguen coincidiendo; preservar cambios previos o concurrentes. Este script no contiene accion Retirar.'
    }
} elseif (-not $program) { $blocks.Add('No se identifico un ejecutable Python real a partir de metadata local verificable.') }

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
[pscustomobject]@{
    SchemaVersion = 1
    Mode = 'SOLO LECTURA; sin escritura, conexiones de prueba, cambios ni parada de procesos'
    Utc = (Get-Date).ToUniversalTime().ToString('o')
    Elevated = $isAdmin
    Interfaces = @($interfaces)
    LocalAddresses = @($addresses)
    DefaultRoutes = @($routes)
    ConnectionProfiles = @($profiles)
    FirewallProfilesActiveStore = @($firewallProfiles)
    Listeners443 = @($listeners)
    PythonExecutableFromVenv = $venvExecutable
    FirewallAllowCandidates = @($firewallCandidates)
    FirewallAssessment = 'Analisis conservador parcial; no es un simulador completo de Windows Filtering Platform. Candidatas no equivalen a permisos efectivos probados.'
    Plan = $plan
    Blockers = @($blocks.ToArray())
    PendingData = @($pending.ToArray())
    Warnings = @($warnings.ToArray())
    ConfirmedFromAnotherNetwork = $false
} | ConvertTo-Json -Depth 9

# Diagnóstico del saludo TCP externo de ServerTec (IPv4/IPv6)

La medición anterior de Pktmon produjo **2 paquetes recibidos y 2 enviados** con
un filtro `TCP SYN`. Esto **no demuestra** que el visitante recibiese SYN-ACK ni
que enviase el ACK final. El filtro SYN tampoco captura necesariamente los ACK
puros. No se repetirán contadores sin propósito: este procedimiento identifica
SYN → SYN-ACK → ACK correlacionando dirección, puerto y números TCP.

**No modifica ServerTec ni su configuración.** No toca certificados, SQLite,
corazones, firewall, NAT, DNS ni claves. Utiliza `pktmon` instalado en Windows,
`pktmon etl2pcap` y Python 3 estándar, sin suscripciones ni instalar software.

## Antes de iniciar

1. Dejar activas **ambas consolas** del menú HTTPS de demostración, escuchando en
   `198.51.100.10:443` y `2001:db8:feed::10:443`.
2. Confirmar que la regla del router TCP 443 y las dos de Windows están activas.
3. Abre **PowerShell como administrador** y ejecuta:

```powershell
pktmon status
pktmon filter list
```

**Detenerse si ya hay una captura activa o filtros de otro trabajo.** `pktmon`
es global en Windows. No se deben sobrescribir ni borrar filtros ajenos.

## 1. Iniciar la captura de cabeceras (una sola vez)

En la **misma** consola de PowerShell administrador:

```powershell
$carpeta = 'D:\Projects\ServerTec\reports\handshake-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
New-Item -ItemType Directory -Path $carpeta -ErrorAction Stop | Out-Null
$etl = Join-Path $carpeta 'captura.etl'
$pcap = Join-Path $carpeta 'captura.pcapng'

pktmon filter add ServerTecHandshakeV4 -i 198.51.100.10 -t TCP -p 443
pktmon filter add ServerTecHandshakeV6 -i 2001:db8:feed::10 -t TCP -p 443
pktmon start --capture --comp nics --pkt-size 80 --file-size 8 --file-name $etl
```

Es una captura **breve, filtrada a TCP 443** y limitada a **8 MiB** de log
circular; registra hasta 80 bytes por trama. Puede incluir direcciones IP,
metadatos y algunos bytes de datos: **los archivos son privados, no compartir
el ETL/PCAPNG ni subirlos a GitHub**. El analizador no imprime esos contenidos.
No usar `--pkt-size 0`, que guardaría paquetes completos.

## 2. Reproducir una sola vez el intento externo

Desde **el Wi-Fi de la otra casa**, mientras la captura sigue activa:

- Intentar `https://203.0.113.10/` para probar **IPv4** sin depender de DNS.
- Si ese dispositivo/red admite IPv6, probar separadamente
  `https://servertec-demo.example.invalid/`. Chrome podría seleccionar IPv4 o IPv6.
- No pulsar «continuar» en advertencias ni modificar las protecciones de Chrome.

No confundir una prueba desde Wi-Fi de tu propia casa con un acceso remoto. El
certificado de demo no es una autoridad reconocida por Chrome.

## 3. Detener y analizar (sin repetir la medición anterior)

Vuelve a la **misma** consola administrador y ejecuta:

```powershell
pktmon stop
pktmon etl2pcap $etl --out $pcap
Set-Location -LiteralPath 'E:\PersonalFiles\Projects\ServerTec'
py -3 .\analizar_handshake.py --pcapng $pcap
```

**Solo si** comprobaste antes que no había filtros ajenos y que nadie añadió
otros durante la prueba, libera los dos filtros con:

```powershell
pktmon filter list
pktmon filter remove
```

`filter remove` elimina **todos** los filtros de Pktmon, no solo los de
ServerTec. Si apareció alguno ajeno, NO ejecutes remove y avisa.

No borres los archivos de captura hasta interpretar los resultados. Guárdalos
localmente en el directorio `reports` protegido, fuera del repositorio Git.

## Interpretación de `status`

| Estado | Qué significa | Diagnóstico siguiente |
|---|---|---|
| `no_se_observo_syn_externo_al_destino_local` | No aparece SYN externo hacia la IP local en la captura | Revisar NAT, ACL del router, WAN, familia IP y alcance de la captura |
| `syn_recibido_sin_synack_correspondiente_observado` | SYN externo entró; no se vio respuesta SYN-ACK correspondiente | Revisar reglas efectivas de Windows y listener exacto |
| `syn_recibido_y_synack_enviado_sin_ack_final_observado` | Se vio la respuesta del PC, no la confirmación del visitante | Revisar trayecto de vuelta/ISP/cliente; el filtro anterior `SYN` no podía descubrirlo |
| `handshake_tcp_confirmado_en_esta_pc` | Llegó el ACK final correcto | TCP funciona en esa familia; investigar TLS/Chrome/HTTP |

El reporte separa IPv4 e IPv6. Deduplica observaciones repetidas por varias
capas NIC, pero **ningún resultado garantiza paquetes no perdidos durante la
captura**. Para IPv6 con encabezados de extensión largos, 80 bytes podrían ser
insuficientes y el analizador no inventará paquetes faltantes.

**No compartas trazas brutas.** Pega aquí solo el JSON resumido que imprime el
analizador, sin adjuntar los archivos `.etl`/`.pcapng`.

## Referencias

- Sintaxis de filtros: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/pktmon-filter-add
- Pktmon start: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/pktmon-start
- Exportación pcapng: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/pktmon-etl2pcap

La utilidad incorpora pruebas automáticas locales: `py -3 -m pytest -q
test_analizar_handshake.py`. Esas pruebas crean paquetes sintéticos y **no
son una captura real en Windows**.

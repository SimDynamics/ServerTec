# Publicación temporal de la demo web: puerto TCP 443

Autorización recibida del propietario: abrir solo TCP 443 por IPv4 e IPv6
para el menú de demostración, manteniendo aislado el backend de ServerTec.

Nombre: https://servertec-demo.example.invalid/
IPv4 WAN: 203.0.113.10; LAN PC: 198.51.100.10.
IPv6 global PC: 2001:db8:feed::10.
Interfaz Ethernet 2, perfil Windows Public.

NO se han ejecutado estos comandos en el PC ni se ha alterado el router.
No usar DMZ, UPnP, desactivar firewall, exponer cuentas o editar PPPoE.
Los certificados de la demo siguen siendo privados: Chrome no confía en
ellos por defecto. No publicar credenciales ni compras en esta etapa.

## Paso 1. Diagnóstico local (PowerShell normal)

Detén con Ctrl+C la demo que escucha en 127.0.0.1:443; no mates otros procesos.

    Set-Location -LiteralPath 'E:\Projects\ServerTec'
    powershell -NoProfile -ExecutionPolicy Bypass -File .\Demo-Web.ps1 -Accion Pruebas
    powershell -NoProfile -ExecutionPolicy Bypass -File .\Reglas-Demo-Publica.ps1 -Accion Plan
    powershell -NoProfile -ExecutionPolicy Bypass -File .\Reglas-Demo-Publica.ps1 -Accion Verificar

Si Plan falla, no continúes: puede haber cambiado una IP, interfaz o perfil.

## Paso 2. Regla Windows (PowerShell como administrador)

    Set-Location -LiteralPath 'E:\Projects\ServerTec'
    powershell -NoProfile -ExecutionPolicy Bypass -File .\Reglas-Demo-Publica.ps1 -Accion Aplicar
    powershell -NoProfile -ExecutionPolicy Bypass -File .\Reglas-Demo-Publica.ps1 -Accion Verificar

El script crea dos reglas persistentes y reversibles, solo para el ejecutable
Python de .venv, Ethernet 2, perfil Public, dirección IP exacta y puerto 443.
Remote Any permite visitantes externos. No asegura que otras reglas preexistentes
no permitan otro tráfico; no toca ninguna regla ajena.

## Paso 3. Iniciar la demo en dos consolas NORMALES

En la ventana IPv4:

    powershell -NoProfile -ExecutionPolicy Bypass -File 'E:\Projects\ServerTec\Demo-Web.ps1' -Accion Iniciar -Nombre 'servertec-demo.example.invalid' -Directorio 'D:\Projects\ServerTec\demo-web-dynv6-20261019' -Direccion '198.51.100.10' -Puerto 443 -ExposicionAutorizada

En otra ventana IPv6:

    powershell -NoProfile -ExecutionPolicy Bypass -File 'E:\Projects\ServerTec\Demo-Web.ps1' -Accion Iniciar -Nombre 'servertec-demo.example.invalid' -Directorio 'D:\Projects\ServerTec\demo-web-dynv6-20261019' -Direccion '2001:db8:feed::10' -Puerto 443 -ExposicionAutorizada

Comprobar:

    Get-NetTCPConnection -LocalPort 443 -State Listen | Select-Object LocalAddress,LocalPort,OwningProcess

Ambos listeners deben estar activos. Si ocurre conflicto, detener la demo
propia con Ctrl+C y comunicar el error; no cambiar a 0.0.0.0 o :: a ciegas.

## Paso 4. Router Sercomm: configurar manualmente sin tocar la WAN PPPoE

En Port Forwarding/NAT/Servidor virtual crear solo una regla nueva:
protocolo TCP, WAN externo 443, destino 198.51.100.10, puerto interno 443.
No permitir UDP ni otros puertos; no modificar la administración remota.
Para IPv6 se requiere regla de entrada en el firewall/ACL del router, TCP443
hacia 2001:db8:feed::10. IPv6 nativa NO usa NAT IPv4.
Mostrar captura de la sección NAT/ACL antes de guardar si los campos difieren.

**Persistencia verificada por el propietario en Sercomm:** al crear una regla,
primero pulsar **Guardar** y luego **Aplicar** en la pantalla de Mapeo de Puertos.
Si solo se pulsa Guardar, la regla puede aparecer temporalmente y desaparecer
tras F5. Tras Guardar + Aplicar, el propietario confirmó que ya permanece.
La persistencia NO demuestra aún que la conexión desde Internet llegue al PC.

Si la LAN cambia por DHCP, actualizar la reserva/destino de forma autorizada.

## Paso 5. Comprobación desde otra conexión

Desde otra PC en una red diferente:

    Test-NetConnection 203.0.113.10 -Port 443
    Test-NetConnection '2001:db8:feed::10' -Port 443

Estos comandos solo prueban TCP. Para Chrome sirve cualquier **otra red**,
incluido el Wi-Fi de otra casa; NO se requieren datos móviles.
Antes de repetir una captura, confirmar las dos escuchas TCP443 y pedir una prueba
externa nueva **después de pulsar Guardar y Aplicar** en el router.
Chrome puede mostrar un error de autoridad, no es prueba de un certificado público.
No aceptar como éxito comercial un certificado no reconocido ni pedir desactivar
las protecciones de los visitantes.

## Retirada

Detener solo las dos consolas de la demo con Ctrl+C. En PowerShell administrador:

    powershell -NoProfile -ExecutionPolicy Bypass -File 'E:\Projects\ServerTec\Reglas-Demo-Publica.ps1' -Accion Retirar
    powershell -NoProfile -ExecutionPolicy Bypass -File 'E:\Projects\ServerTec\Reglas-Demo-Publica.ps1' -Accion Verificar

En el router, retirar exclusivamente las reglas NAT y ACL temporales nuevas.
No ejecutar Inicializar ni tocar D:\Projects\ServerTec\state.
No se implementó ningún plan de pago, freemium, ni cuota futura.

Estos cambios solo agregan código al repositorio. Ninguna regla de Windows
ha sido instalada ni probada en ejecución desde esta sesión.

## Diagnostico nuevo: SYN, SYN-ACK y ACK

Los dos paquetes de la prueba anterior con filtro TCP SYN no prueban el ACK final.
La guia [HANDSHAKE-EXTERNO.md](HANDSHAKE-EXTERNO.md) ofrece una captura breve
con Pktmon, separada por IPv4/IPv6. El analizador `analizar_handshake.py`
genera solo un resumen sin direcciones IP de visitantes ni datos capturados.
Las trazas brutas nunca se suben a Git; el script se probo sobre paquetes sinteticos.
No cambiar el router ni los servidores existentes para repetir contadores.

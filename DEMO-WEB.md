# Menú LearnGraphicsProgramming: estado actual y QA anterior

## Instrucción vigente: acceso público sin preparar visitantes

El nuevo prompt del 2026-10-19 **reemplaza** la exigencia de conservar `.dynamics`
y configurar los visitantes. Autoriza evaluar nombre público y CA reconocida
por Chrome bajo la condición de ausencia de pagos presentes/futuros, sin freemium,
facturación ni la CA expresamente excluida. No hace falta volver a solicitar esa
autorización de investigación; las cuentas, acuerdos y cambios de red concretos
siguen requiriendo autorización antes de aplicarlos.

La [evaluación actual](EVALUACION-ACCESO-PUBLICO.md) no acreditó una combinación
compatible. No se ha obtenido URL pública ni integrado dependencia externa.
La demo conservada pasó de nuevo 171 pruebas y el backend su AutoPrueba 9/9.
Actualmente no hay listener443. No se ha probado acceso Chrome por Internet.

Lo que sigue es el **procedimiento y evidencia de la QA privada anterior**,
conservados para referencia. Sus pasos de hosts, CA propia o DNS en Android
**no son la solución del objetivo público vigente** y no se aplican a visitantes.

## Antecedentes: ensayo privado anterior

URL prevista y conservada: **https://learngraphicsprogramming.dynamics/**.
El nombre es una asociación PRIVADA en cada cliente de prueba; no se ha registrado
en Internet. Esta demo no integra el currículo ni Android.

## Aclaración de alcance: cualquier usuario remoto

El usuario aclaró el 2026-10-19 que el acceso debe servir para cualquier usuario
Windows/Android con Chrome, sin limitarlo a la IP de un dispositivo concreto.
Las plantillas de origen /128 o /32 que aparecen más abajo son el ensayo
restringido anterior, **no un requisito del nuevo objetivo general**. No se han
aplicado esas reglas. La apertura pública de solo TCP443 hacia el listener demo
sería un cambio específico a revisar y autorizar; nunca se publica la API completa.

El usuario confirmó que cualquiera debe abrir la URL directamente, sin preparar
su dispositivo, como ensayo real para una futura aplicación comercial. Ese
objetivo es incompatible con las dos condiciones originales siguientes:

- `.dynamics` no figura en la [lista actual de TLD delegados de IANA](https://data.iana.org/TLD/tlds-alpha-by-domain.txt)
  (versión 2026101800). Resolver `dynamics.` NS y el nombre completo A desde el DNS
  normal de esta PC devolvió `DNS_ERROR_RCODE_NAME_ERROR` el 2026-10-19. Cambiar
  nuestro router/hosts no registra este nombre en el DNS público de otros usuarios.
- La CA propia no forma parte de la confianza predeterminada de otros Chrome.
  El [modelo oficial de Chrome](https://chromium.googlesource.com/chromium/src/+/main/net/data/ssl/chrome_root_store/faq.md)
  exige una autoridad reconocida o una decisión de confianza local del usuario.
  Instalarla solo en nuestra PC no modifica los navegadores remotos.

Se puede preparar un procedimiento común para clientes sin vincularlos a IP
individual; cada cliente tendría que configurar resolución y confianza si se
conservan el nombre privado y la CA propia. No se ha anunciado acceso público
sin configuración y no se sustituye silenciosamente la URL, CA o infraestructura.
La preparación individual fue descartada por el usuario para el objetivo público.
Se pidió autorización para EVALUAR cambios de nombre público y confianza de
certificado. El usuario eligió expresamente **«Mantener las restricciones
originales»**. Se conserva por tanto la URL exacta, CA propia y prohibiciones de
infraestructura externa. El acceso universal sin preparación queda **bloqueado
por incompatibilidad de requisitos**, no pendiente de más cambios de código.
No procede presentar apertura de router/firewall o configuración de un teléfono
como cumplimiento del objetivo público sin preparar clientes. No se reiterará
la solicitud de cambiar esas restricciones sin una nueva instrucción del usuario.

El servidor y sus datos pueden seguir en esta PC. No se compró, contrató, registró
ni publicó nada; no se eligió silenciosamente un proveedor o una URL sustituta.

Diagnóstico adicional, ejecutable desde cualquier consola (solo lectura):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File 'E:\Projects\ServerTec\Diagnostico-Demo-Externa.ps1'
```

Para revisar el alcance de un posible permiso público IPv6, sin aplicarlo:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File 'E:\Projects\ServerTec\Diagnostico-Demo-Externa.ps1' -DireccionServidor '2001:db8:feed::10' -AccesoGeneral
```

Produce `RemoteAddress=Any` únicamente como borrador de todas las direcciones de
Internet hacia TCP443/IP/interfaz/programa concretos. `ReadyToApply=false` y
`PendingExplicitApproval=true`; no tiene acciones Aplicar/Retirar. Una dirección
IPv6 local y un borrador no acreditan acceso desde otra red, resolución o Chrome.

En esta continuación, `Comprobar` confirmó la ejecución iniciada POR EL USUARIO:
`run_id=81cd8b3eda7c510b0b6700b1b950cb28`, listener `127.0.0.1:443`, PID3488.
No se detuvo ni reinició ese proceso. El panel web identifica un Sercomm GPON;
la foto facilitada identifica modelo FG6122TM. Se abrió solo la pantalla de login,
sin usar ni repetir contraseñas de la etiqueta y sin cambiar configuración.

## Estado y límites de la entrega

- **Funciona localmente:** menú, estado fresco y HTTPS con validación de cadena
  y nombre mediante sockets reales. Se prueba TCP 443, sin sustituirlo por 8443.
- **Software preparado para prueba externa:** listener opcional, material TLS
  independiente, comandos y retirada. La exposición de red sigue desactivada.
- **Confirmado desde otra red: NO.** Faltan conectividad entrante, asociaciones
  de nombre y confianza autorizadas, y las pruebas del usuario en Windows/Android.
- **Validación real en Chrome: pendiente.** Una herramienta con CA explícita no
  sustituye Chrome. La automatización de interfaz se detuvo al no poder determinar
  con suficiente confianza la URL de la ventana; no se importó confianza.

Base local: `main`, `ec0abbc444ddb99841390a4c0ffa4916aa5baa49`, árbol inicialmente
limpio. No se ejecutaron operaciones Git de escritura sobre este repositorio.
No se modificaron backend, contratos, catálogo, dependencias, Android ni Work.
Las pruebas históricas que crean repositorios Git usan fixtures temporales.

Se leyeron README.md, RESULTADOS.md, AUTENTICACION.md, HISTORIALES.md y
EVALUACIONES.md antes de implementar. Cuentas, recuperación, sesiones, dispositivos,
saldos compartidos, transacciones, A → B → A y recuperación de corazones bajo
demanda permanecen en el backend original. La demo ni siquiera lo importa.

Las tres rutas candidatas de estado comprobadas no existen en esta PC:
`D:\Projects\ServerTec\state`, `E:\Projects\ServerTec\state` y
`%LOCALAPPDATA%\ServerTec\state`. **No se inicializó ninguna**, no se abrió una
SQLite real y no se copiaron bases abiertas, claves ni certificados anteriores.

## Archivos y exposición

Nuevos: `demo_web.py`, `demo_pki.py`, `demo_check.py`, `Demo-Web.ps1`,
`Diagnostico-Demo-Externa.ps1`, este documento,
`demo_web_assets/index.html`, `menu.css`, `menu.js` y tres `test_demo_*.py`.
README.md enlaza esta demo; RESULTADOS.md conserva la evidencia de esta ejecución.

`ServerTec.ps1` y `manage.py` conservan su arranque normal y bloqueo de loopback.
La demo se inicia expresamente en otro proceso, sin montar la aplicación completa.
Solo admite estas rutas literales:

| Ruta | Métodos | Contenido |
|---|---|---|
| `/` | GET, HEAD | Menú |
| `/menu.css` | GET, HEAD | Estilo local |
| `/menu.js` | GET, HEAD | Botones y consulta local |
| `/demo/status?challenge=...` | GET | Hora UTC, eco aleatorio, ejecución y petición |

No hay login, negocio, subida, compilador, directorios publicados, Swagger,
service workers, recursos remotos ni redirección HTTP. Rutas ajenas reciben 404.
Los dos botones de rutas muestran «Demostración: contenido todavía no integrado».
El botón de conexión consulta una respuesta nueva con `fetch` sin caché, challenge
aleatorio, hora del servidor, `run_id` público por proceso y `request_id` por petición.
Las respuestas llevan no-store y CSP. No hay HSTS/preload. Hay límites modestos
de cabeceras, cuerpo, peticiones y concurrencia; no acreditan resistencia a carga
o ataques de Internet de una aplicación de producción.

## Preparar, iniciar, comprobar y detener

PowerShell normal, dependencias existentes de `.venv`; no instalar nada nuevo:

```powershell
Set-Location -LiteralPath 'E:\Projects\ServerTec'
powershell -NoProfile -ExecutionPolicy Bypass -File .\Demo-Web.ps1 -Accion Rutas
powershell -NoProfile -ExecutionPolicy Bypass -File .\Demo-Web.ps1 -Accion Inspeccionar
```

El material final ya está preparado en `D:\Projects\ServerTec\demo-web-20261019`.
Raíz final, huella SHA-256 **DER**:
`dc4823f93b922cb013b98f183d9d09bc2aac19cf6c036caaace71b33f2d9501e`.
La hoja/intermedia caducan el `2026-10-26T05:59:59Z`. La raíz caduca el
`2026-11-18T05:59:59Z`; esto no amplía la vigencia de la hoja.
**No repetir Preparar sobre una carpeta existente.** Para reproducir en una
carpeta NUEVA (el comando rechaza reemplazos):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Demo-Web.ps1 -Accion Preparar -Directorio 'D:\Projects\ServerTec\demo-web-otra-prueba' -AutoridadDesechable
```

`-AutoridadDesechable` firma en memoria y no conserva las claves privadas de la
raíz ni de la intermedia. El modo sin ese switch pide una frase local con getpass
y conserva solo la raíz cifrada; **no es el modo preparado para este ensayo**.
La intermedia nunca conserva su clave. No se suministra una contraseña universal.

Iniciar el material final en loopback, en primer plano:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Demo-Web.ps1 -Accion Iniciar
```

En otra consola:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File 'E:\Projects\ServerTec\Demo-Web.ps1' -Accion Comprobar
```

Esta ruta absoluta funciona aunque esa segunda consola empiece en
`C:\Users\GameDev`; no exige repetir Set-Location. Un error «el argumento -File
no existe» antes de iniciar Python corresponde a la ubicación del script, no a
la red, los certificados ni el listener.

Comprobar conecta a la IP literal `127.0.0.1:443`, pero valida SNI y nombre TLS
`learngraphicsprogramming.dynamics` con la CA indicada. No modifica hosts y no
acredita DNS ni Chrome. Para detener: **Ctrl+C en la consola que inició la demo**.
No buscar y matar procesos por nombre o puerto. El arranque no instala un servicio
ni una tarea programada; no queda listener de la sesión de QA al entregar.

Equivalentes directos:

```powershell
.\.venv\Scripts\python.exe demo_web.py serve --enable-demo --host 127.0.0.1 --port 443 --cert 'D:\Projects\ServerTec\demo-web-20261019\runtime\server.pem' --key 'D:\Projects\ServerTec\demo-web-20261019\runtime\server-key.pem'
.\.venv\Scripts\python.exe demo_check.py --directory 'D:\Projects\ServerTec\demo-web-20261019' --address 127.0.0.1 --port 443
```

## Certificados propios y entrega controlada

Solo copiar al cliente **`public\authority.cer` o `public\authority.pem`** desde
la PC mediante un medio controlado, por ejemplo USB. Comparar su huella SHA-256
con `Inspeccionar` en la PC o con el valor comunicado por una vía ya confiable.
No descargar la CA desde la web que todavía se intenta autenticar.

`public\metadata.json` distingue:

- `authority_certificate_sha256`: SHA-256 del certificado DER; coincide con la
  huella SHA-256 del visor. `Get-FileHash public\authority.cer -Algorithm SHA256`
  coincide porque ese archivo contiene DER.
- `authority_pem_file_sha256`: hash de los bytes del archivo PEM, **otro valor**.
- Las huellas de hoja/intermedia y de la cadena se identifican por separado.

La clave del servidor se guarda bajo `runtime` fuera del repositorio, con ACL
para usuario actual, SYSTEM y administradores. La clave de la CA no se sirve ni
se necesita al iniciar; en el material preparado ni siquiera se conservó.
`runtime\server.pem` contiene hoja e intermedia públicas, nunca una clave CA.
No copiar `runtime`, `authority` ni el directorio completo al cliente.

La hoja tiene SAN **único y exacto** `learngraphicsprogramming.dynamics`, EKU de
servidor y siete días de vigencia. La raíz admite una intermedia; la intermedia
incluye restricciones críticas: DNS permitido apex, DNS excluido `.apex` para
sus descendientes, e IP excluidas `0.0.0.0/0` y `::/0`. Las pruebas comprueban que
la intermedia rechaza subdominios, otros DNS e IP aunque la raíz no restrinja.
Un SAN de la hoja por sí solo no limita una autoridad completa.

Importar **solo la raíz pública**, nunca la intermedia como nueva ancla de
confianza. En Android una raíz importada puede ignorar sus propias restricciones;
las de una intermedia se evalúan dentro de la cadena. Instalar una raíz sigue
siendo una decisión de confianza en el almacén del usuario de Android, no una
preferencia exclusiva de Chrome. Las claves de emisión desechadas reducen el
material capaz de producir otras cadenas, pero no cambian el alcance del almacén.

No usar flags que omitan validación, excepciones de certificado, curl -k,
verify=False, ni cambiar Safe Browsing o «Usar siempre conexiones seguras».
Si cambia la IP y el nombre permanece, se actualizan las asociaciones y reglas
de red, no el SAN. Tras caducar, retirar la CA de clientes y preparar una nueva
identidad en otra carpeta; esta herramienta no sobrescribe ni renueva identidades.

## Diagnóstico de red observado

Ethernet 2, perfil Windows **Public**, puerta de enlace IPv4 `198.51.100.1`:

| Dato | Observado | Qué demuestra |
|---|---|---|
| IPv4 PC | `198.51.100.10/24` | Dirección privada, no la WAN |
| IPv6 global PC | `2001:db8:feed::10/64` | Dirección candidata, acceso externo no probado |
| IPv6 temporal | `2001:db8:feed::11` | Puede cambiar; evitar fijarla sin revisar |
| Rutas por defecto | IPv4 e IPv6 en Ethernet 2 | Salida configurada, no permiso de entrada |
| TCP 443 | Libre antes y después de QA; ocupado solo por nuestra demo durante ella | Puerto local disponible |
| Firewall efectivo | Activo, entrada Block; no regla específica Python/ServerTec/443 encontrada | No se ha autorizado apertura |
| portproxy | Sin entradas | No hay encaminamiento local oculto |
| IPv4 WAN / CGNAT | **No determinado** | Falta leer estado Internet/WAN del router |
| Router TCP 443 / ACL IPv6 | **No determinado** | El acceso HTTP de solo lectura devolvió 400; no se autenticó ni cambió el router |

No se consultó una API externa para averiguar la IP pública. La dirección WAN del
router debe cotejarse con su conectividad: rangos privados o `100.64.0.0/10` indican
NAT adicional/posible CGNAT; una WAN aparentemente pública tampoco demuestra que
el proveedor permita entrada. Una IPv6 global no demuestra accesibilidad ni que
la red móvil disponga de IPv6 compatible. No usar `198.51.100.10` en un cliente remoto.

## Cambios de Windows/router pendientes de autorización

**Ninguno de estos cambios se aplicó.** Elegir UNA familia de red tras conocer
la dirección externa del cliente. No autorizar destinos/remotos comodín.

IPv6: mantener la URL exacta en TCP443 y enlazar únicamente la IPv6 vigente de la
PC. Tras autorizar esa exposición concreta:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Demo-Web.ps1 -Accion Iniciar -Direccion '2001:db8:feed::10' -ExposicionAutorizada
```

La regla propuesta Windows (PowerShell elevado por el usuario) debe fijar
`Name=ServerTec-Demo-Web-20261019-v6`, `Direction=Inbound`, `Action=Allow`,
`Protocol=TCP`, `LocalPort=443`, `LocalAddress=IPv6_PC`, `RemoteAddress=IPv6_CLIENTE/128`,
`Profile=Public`, `InterfaceAlias=Ethernet 2`, `EdgeTraversalPolicy=Block` y el
ejecutable Python REAL que posee el socket. En esta instalación es el Python313
de `%LOCALAPPDATA%\Programs\Python\Python313\python.exe`, no necesariamente el
launcher `.venv`. Verificar PID/ExecutablePath al iniciar. Si ya existe ese nombre
de regla, detenerse; no sobrescribirlo.

Plantilla del cambio concreto (no ejecutada; reemplazar el origen y revisar antes
de autorizar, sin convertirlo en `Any`):

```powershell
$demoClientIPv6 = [Net.IPAddress]::Parse('REEMPLAZAR_POR_IPV6_PUBLICA_DEL_CLIENTE')
if ($demoClientIPv6.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetworkV6) { throw 'Se necesita IPv6 del cliente' }
if (Get-NetFirewallRule -Name 'ServerTec-Demo-Web-20261019-v6' -ErrorAction SilentlyContinue) { throw 'Ya existe esa regla; no reemplazar' }
New-NetFirewallRule -Name 'ServerTec-Demo-Web-20261019-v6' -DisplayName 'ServerTec demo web temporal' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 443 -LocalAddress '2001:db8:feed::10' -RemoteAddress ($demoClientIPv6.ToString() + '/128') -Profile Public -InterfaceAlias 'Ethernet 2' -Program "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -EdgeTraversalPolicy Block
```

El valor pendiente de origen impide dar por autorizada/aplicada esa plantilla.

El router necesita permitir entrada TCP443 hacia esa IPv6 concreta. No hay NAT
IPv6/port forwarding IPv4 implicado en esa vía. Revisar límites por origen del
router antes de autorizar su alcance. Retirar solo la regla añadida:

```powershell
Remove-NetFirewallRule -Name 'ServerTec-Demo-Web-20261019-v6'
```

IPv4 alternativa: primero confirmar WAN pública enrutable y ausencia de CGNAT
impeditivo. Autorizar después TCP443 externo → `198.51.100.10:443` en router y una
regla Windows igualmente puntual (LocalAddress IPv4 PC, RemoteAddress IPv4 pública
del cliente, nombre terminado `-v4`). Enlazar la demo a `198.51.100.10`; no la API.
Si el router reserva 443 para administración, resolver ese conflicto explícitamente.
No se cambian router, DHCP ni reservas en esta entrega. No se necesita portproxy:
la demo escucha directamente 443. No se ofrecen DMZ, UPnP, túneles o puertos amplios.

## Cliente Windows externo, tras autorización

1. Obtener dirección vigente y conectividad pública de la familia elegida. Debe
   estar en otra red. Conservar el hosts anterior antes de editarlo; comprobar
   primero que no contiene ya el nombre para no pisar asociaciones existentes.
2. Cambio puntual propuesto en `%SystemRoot%\System32\drivers\etc\hosts`:

   ```text
   2001:db8:feed::10 learngraphicsprogramming.dynamics # ServerTec-Demo-Web-20261019
   ```

   Para IPv4 usar en esa línea la WAN PÚBLICA verificada, nunca la privada de PC.
   Para QA de Chrome en la propia PC, la línea es `127.0.0.1` con el mismo nombre
   y marcador. No añadir ambas familias si una todavía no funciona.
   Retirada: eliminar únicamente la línea marcada; preservar cualquier otro cambio.
   Vaciar la caché DNS del cliente después si conserva la asociación anterior.
3. Comprobar A, resolución efectiva usando el resolvedor del sistema (no nslookup,
   que consulta DNS y no acredita hosts):

   ```powershell
   [System.Net.Dns]::GetHostAddresses('learngraphicsprogramming.dynamics')
   Test-NetConnection learngraphicsprogramming.dynamics -Port 443
   ```

   La segunda prueba comprueba B, conexión TCP; todavía no acredita C, Chrome/TLS.
4. Usar Chrome con un `--user-data-dir` NUEVO y dedicado, sin inicio de sesión ni
   sincronización. Incógnito comparte la confianza del perfil original. Ejemplo
   en esta PC (ajustar ruta real del Chrome externo):

   ```powershell
   & "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe" --user-data-dir=D:\Projects\ServerTec\demo-web-chrome-test --no-first-run chrome://certificate-manager/
   ```

5. Revisar versión y `chrome://policy`. Chrome aquí instalado: **155.0.8059.84**;
   registro sin políticas relevantes de certificados/DNS/HTTPS, pero no se pudo
   comprobar la página de políticas efectiva. En el perfil de prueba, gestor
   `chrome://certificate-manager` → certificados locales/usuario → confianza
   personalizada: importar SOLO la raíz pública tras comparar la huella DER.
   No usar el almacén global Windows ni el perfil personal. Revisar restricciones
   del certificado y del gestor. DNS apex en el gestor incluye descendientes;
   campos IP vacíos **no significan denegar IP**. Esta cadena añade la exclusión
   crítica de descendientes y de ambas familias IP en la intermedia.
6. Abrir **https://learngraphicsprogramming.dynamics/** sin puerto, sin saltar
   avisos. Chrome debe validar cadena, vigencia y nombre. Probar ambos botones de
   contenido y pulsar conexión dos veces: misma ejecución, respuestas distintas.
   Registrar hora/ejecución; contrastar ejecución con consola del servidor.
7. Retirar la raíz identificada por huella desde ESE perfil, cerrar solo ese Chrome
   y retirar su carpeta de prueba si ya no se necesita; no borrar perfiles personales.

## Cliente Android externo, límites y configuración pendiente

El usuario confirmó Android y Windows con Chrome. Faltan versión Android y Chrome
del teléfono; no se usó Honor, ADB ni ningún dispositivo de Work.

Android estándar no ofrece la edición puntual de hosts de Windows sin root.
«DNS privado» configura un proveedor, no una entrada hosts para este nombre.
No basta con instalar el certificado: sin asociación de nombre la URL no resolverá.
La entrega **no declara Android listo para abrir la URL**.

Una opción investigada es **personalDNSfilter**, software GPLv2 que ejecuta una
VPN DNS local sin root ni servidor VPN externo. No se instaló ni probó en el
teléfono. Una regla local posible en «additional hosts» es:

```text
>learngraphicsprogramming.dynamics IP_PUBLICA_VERIFICADA
```

Requiere aceptar una aplicación y permiso VPN local (ocupa la plaza VPN de Android),
activar `enableLocalResolver=true`, mantener proxy DNS remoto/root desactivados y
revisar A/AAAA y consultas HTTPS. Sus valores por defecto incluyen actualizaciones
de listas, DNS de respaldo, registro y autoarranque; **no usarlos como configuración
lista de este ensayo**. Habría que dejar autoarranque y registros desactivados,
sin listas/actualizaciones ni control remoto, y comprobar resolución local sin
dependencia de servicios externos para el menú. Chrome DNS seguro o DNS privado
pueden eludir esa asociación: no modificarlos sin mostrar el ajuste y autorización.
No desactivar Safe Browsing ni HTTPS seguro. Se documenta como candidato pendiente,
no como una receta ya verificada o software necesario para el servidor.

Chrome Android no tiene este gestor de confianza aislado por perfil de escritorio.
Instalar una CA mediante Ajustes de Android la añade al usuario/perfil Android y
puede afectar otras apps que acepten autoridades de usuario. **Ese alcance debe
aceptarse expresamente antes de instalar.** Preferir un usuario Android de prueba
si el dispositivo lo permite; no asumir que todos ofrecen usuarios secundarios.
Copiar solo la raíz por USB, comparar huella y usar la instalación CA que ofrezca
la versión del teléfono. No importar la intermedia. Confirmar realmente en Chrome
sin interstitial; si no valida o las políticas impiden la operación, detenerse.

Retirada Android: detener VPN local y quitar solo la regla local; restaurar los
ajustes DNS anteriores si se hubieran autorizado, retirar únicamente la CA de
esta demo por huella en credenciales de usuario, y quitar la app/perfil de prueba
si se creó exclusivamente para ello. Sin root, desbloqueo del bootloader ni cambios
del proyecto Android. Si no se acepta ese alcance, Android permanece bloqueado
para este nombre privado bajo las restricciones actuales.

## Ensayo externo y reversión

Con Wi-Fi desactivado y datos móviles, o desde Windows en una red ajena:
comprobar por separado A nombre → IP correcta, B TCP443 entrante, C Chrome valida
certificado. Después probar menú y respuesta actual, desconectar la red y volver
a pulsar: debe mostrar fallo, nunca un éxito de caché. Restaurar red y repetir.
Registrar SO/Chrome, tipo de red, familia IP, fecha/hora y run_id. Un teléfono en
el mismo Wi-Fi o una prueba hacia la propia WAN no acreditan acceso externo.

Al terminar: Ctrl+C demo, retirar solo reglas nuevas Windows/router, la línea
hosts marcada, raíz de prueba y configuración Android autorizada. No hay servicio,
tarea ni confianza global Windows creados por esta entrega. Si se retira material
TLS, comprobar primero la ruta exacta y que pertenece solo a esta demo; no tocar
`state`, certificados productivos, otros perfiles ni reglas existentes.

Durante la tarea se creó también `D:\Projects\ServerTec\demo-web` para una
primera QA TLS, antes de reforzar la cadena Android; **no usar ni confiar esa
identidad anterior**. No tiene claves emisoras conservadas. El perfil aislado
`D:\Projects\ServerTec\demo-web-chrome-profile` quedó cerrado y sin CA importada;
la retirada de su carpeta fue rechazada por el control automático («blocked by
policy»). No se intentó sortearlo. Ambas carpetas pertenecen a esta tarea,
están fuera del estado real y no son directorios web ni servicios activos.

Si cambia IP pública/IPv6/prefijo, actualizar manualmente hosts/override de cada
cliente, dirección bind y reglas de destino Windows/router; si cambia IPv4 privada,
también el destino NAT. Revisar IP externa de origen si la regla la limita. No hay
actualización automática de IP ni publicación de DNS en este ensayo.

Pruebas y resultados actuales: [RESULTADOS.md](RESULTADOS.md), sección de demo web.

## Fuentes primarias consultadas

- [Chrome Root Store: autoridades locales y gestor](https://chromium.googlesource.com/chromium/src/+/main/net/data/ssl/chrome_root_store/faq.md).
- [Chrome 155: restricciones de anclas personalizadas](https://chromium.googlesource.com/chromium/src/+/refs/tags/155.0.8059.84/net/cert/cert_verify_proc_builtin.cc).
- [Base de certificados por perfil; incógnito comparte original](https://chromium.googlesource.com/chromium/src/+/refs/tags/155.0.8059.84/chrome/browser/net/server_certificate_database_service_factory.cc).
- [Chrome 155: raíces añadidas en Android](https://chromium.googlesource.com/chromium/src/+/refs/tags/155.0.8059.84/net/cert/internal/trust_store_android.cc).
- [BoringSSL usado por Chrome 155: semántica de restricciones DNS](https://boringssl.googlesource.com/boringssl/+/b780f192ce515ed8ed358f6c0947bd7acce438b9/pki/name_constraints.cc).
- [BoringSSL: validación de restricciones en intermedias](https://boringssl.googlesource.com/boringssl/+/b780f192ce515ed8ed358f6c0947bd7acce438b9/pki/verify_certificate_chain.cc).
- [Android: DNS privado](https://support.google.com/android/answer/9654714).
- [personalDNSfilter: proyecto local y licencia](https://github.com/IngoZenz/personaldnsfilter), [reglas adicionales](https://github.com/IngoZenz/personaldnsfilter/blob/38951ab6b6edae40fa80cfae630ae4aaec89fcbd/app/src/main/assets/additionalHosts.txt), [FAQ y límites VPN/DNS](https://www.zenz-solutions.de/faq/).

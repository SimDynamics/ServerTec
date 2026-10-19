# Resultados verificados de ServerTec

## 2026-10-19 — Evaluación pública autorizada, sin pagos futuros

La nueva instrucción sustituye la obligación del nombre privado y la preparación
de visitantes. Permite investigar nombre público y CA reconocida, manteniendo
PC/datos locales y la condición económica estricta. Las decisiones privadas de
las secciones inferiores son **históricas**, no restricciones aún vigentes.

Se revalidó raíz real E:\PersonalFiles\Projects\ServerTec, rama main y HEAD
ec0abbc444ddb99841390a4c0ffa4916aa5baa49, y se conservaron todos los cambios
existentes. No se hicieron operaciones Git de escritura ni repositorios nuevos.
En esta ejecución solo cambió documentación: README.md, DEMO-WEB.md, este archivo
y el nuevo EVALUACION-ACCESO-PUBLICO.md. No hubo integración externa ni cambios
del código, dependencias, backend, PKI, Android, Work, Premium o datos reales.

Conclusión: **no se ha verificado una combinación compatible**, sin afirmar la
inexistencia universal de alternativas. El nombre candidato deSEC/dedyn.io no
puede darse por obtenido: su aviso vigente suspende nuevas asignaciones. Google
Public CA es técnicamente apta y anuncia solicitudes sin cargo, pero CP/CPS TLS
6.10 §9.1.1 permite cargos de emisión, gestión y renovación. No se asume gratuidad
comercial futura ni sustitución posterior por pago/otro proveedor gratuito.
También se contrastaron otras ofertas, con sus condiciones y límites; fuentes
y brechas concretas en EVALUACION-ACCESO-PUBLICO.md.

No se crearon cuentas, aceptaron acuerdos, solicitaron certificados, asignaron
nombres, activó facturación ni adquirió compromiso de contratación. Tampoco se
modificaron firewall/router/hosts/confianza, publicaron rutas de negocio o
instalaron clientes ACME/DDNS, servicios, tareas o automatizaciones provisionales.

Pruebas NUEVAS realmente ejecutadas en Windows/Python3.13.2 con estado temporal:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
powershell -NoProfile -ExecutionPolicy Bypass -File 'E:\PersonalFiles\Projects\ServerTec\Demo-Web.ps1' -Accion Pruebas
powershell -NoProfile -ExecutionPolicy Bypass -File 'E:\PersonalFiles\Projects\ServerTec\ServerTec.ps1' -Accion AutoPrueba
```

Resultado demo: **171 passed en 8,27 s**. Backend original: **AutoPrueba 9/9**,
HTTPS, proceso y SQLite reales de QA; estado temporal eliminado. No se abrió
ninguna SQLite real. No se presenta la batería histórica completa como ejecutada
ahora y no se usaron fixtures que crearan repositorios Git.

`Diagnostico-Demo-Externa.ps1` terminó correctamente en solo lectura, sin avisos.
Instantánea 2026-10-19T14:15:04Z: Ethernet2 198.51.100.10/24 DHCP, gateway
198.51.100.1; IPv6 estable candidata 2001:db8:feed::10/64 y
temporal nueva 2001:db8:feed::12; rutas por defecto de ambas
familias; perfil Public, firewall activo y entrada Block. **Sin listeners443 ni
proceso de demo activo**. El PID3488 descrito antes ya no está sirviendo; esta
ejecución no lo detuvo. No se instalaron servicios/tareas ni entradas portproxy.

State D, repo y LOCALAPPDATA siguen ausentes; solo se comprobó existencia. No se
inicializó estado ni leyó/regeneró claves. La configuración IPv4 WAN/CGNAT,
entrada router y llegada externa siguen desconocidas; IPv6 local no es evidencia
de compatibilidad universal. Se documentaron los fallos de continuidad actuales:
sin autoarranque tras reinicio, sin actualización DNS y sin renovación pública.

Estado actual: **funciona localmente en pruebas**; listener detenido.
**Preparado para prueba externa pública: NO. Confirmado públicamente en Chrome
sin preparar al visitante: NO.** Se mantiene la condición económica solicitada,
sin rebajarla ni ofrecer una solución de pago o privada como sustituto.

## 2026-10-19 — Continuación y alcance público comercial

El usuario inició la demo loopback y pidió continuar hasta acceso desde Chrome
para cualquier usuario Android/Windows, sin preparar su dispositivo. No se
reinterpreta ese objetivo como whitelist de una IP de prueba ni como un teléfono
con CA/DNS instalados previamente.

Se comprobó otra vez raíz real, main, HEAD ec0abbc444ddb99841390a4c0ffa4916aa5baa49
y cambios locales de la entrega anterior. Se preservaron todos. El proceso del
usuario PID3488 sigue en 127.0.0.1:443, ejecutable Python313 real, sin detenerlo
ni reiniciarlo. El comando absoluto desde otra ubicación:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File 'E:\PersonalFiles\Projects\ServerTec\Demo-Web.ps1' -Accion Comprobar
```

pasó las cuatro comprobaciones; run_id `81cd8b3eda7c510b0b6700b1b950cb28`, hora
observada `2026-10-19T06:14:20.368610Z`. Es la misma ejecución que luego confirmó
el usuario. `dns_or_chrome_verified` sigue false. Se corrigió la documentación
para evitar el error de -File relativo en una segunda consola con otro cwd.

Diagnóstico adicional de solo lectura: direcciones/rutas Ethernet2 sin cambios,
perfil Public, firewall efectivo activo con entrada Block, sin elevación actual.
El panel HTTP del router cargó en navegador la pantalla de login Sercomm GPON;
la foto identifica FG6122TM. No se usaron contraseñas de la etiqueta ni se inició
sesión, cambió router, abrió firewall, editó hosts o instaló confianza.

Bloqueo DNS/trust confirmado antes de afirmar disponibilidad pública:

- [IANA](https://data.iana.org/TLD/tlds-alpha-by-domain.txt), lista versión2026101800,
  no incluye DYNAMICS. Se consultó también su base de la zona raíz.
- Resolve-DnsName dynamics. NS y learngraphicsprogramming.dynamics. A con DNS
  normal, sin hosts, devolvieron DNS_ERROR_RCODE_NAME_ERROR.
- El [modelo oficial de confianza de Chrome](https://chromium.googlesource.com/chromium/src/+/main/net/data/ssl/chrome_root_store/faq.md)
  requiere una CA reconocida o confianza local; generar nuestra CA no modifica
  la confianza de Chrome de otros usuarios.

Por tanto, no es posible cumplir acceso universal sin preparar clientes a la URL
exacta privada y con CA propia de la solicitud inicial. Se solicitó autorización
para evaluar el cambio de esas dos restricciones, conservando el servidor local
y sin comprar, contratar o publicar nada. No se eligieron proveedor o dominio
sustitutos ni se presentó la conectividad del router como remedio de DNS/trust.
El usuario respondió expresamente «Mantener las restricciones originales».
Se conserva esa decisión: acceso universal sin preparación BLOQUEADO por
incompatibilidad de nombre privado/CA propia con Chrome sin configurar.
No se reitera la solicitud ni se abre red como supuesto cumplimiento.

Se añadió Diagnostico-Demo-Externa.ps1 como herramienta exclusivamente de lectura
y borradores, sin acciones Aplicar/Retirar ni conexiones nuevas. `-AccesoGeneral`
identifica explícitamente un borrador para todas las IP solo en TCP443/IPinterfaz/
programa concretos, nunca autorización ni apertura ejecutada. Las plantillas
restringidas previas son opcionales y no representan el objetivo general.
La aclaración queda también al inicio de DEMO-WEB.md. No se repitió la batería
Python por un cambio exclusivamente de documentación/diagnóstico PowerShell.
Se ejecutó el nuevo script con PowerShell5.1 real: diagnóstico sin parámetros,
borrador general IPv6, borrador restringido opcional con origen sintético sin
conectarse, IPv4 sin WAN (sin plan) y rechazo de origen privado. Todos dieron el
resultado esperado. Se comprobó sintaxis, ASCII compatible y git diff --check.
La revisión conservadora de reglas no declara sus candidatas como permisos
efectivos de Python. Al cierre siguen 0 reglas de demo y PID3488 intacto.

## 2026-10-19 — Demo web exclusivamente local, Windows real

Repositorio `E:\PersonalFiles\Projects\ServerTec`, `main` local, HEAD inicial y
final `ec0abbc444ddb99841390a4c0ffa4916aa5baa49`. Árbol inicialmente limpio;
entrega sin staging, commits, ramas ni operaciones de red Git en este checkout.
Solo se añaden archivos de la demo y se amplía documentación. Backend, contratos,
catálogo, dependencias, Android y Work no cambiaron.

Entorno realmente utilizado: Windows, PowerShell 5.1 (wrapper), Python **3.13.2**,
OpenSSL **3.0.15**, cryptography **46.0.4**, FastAPI **0.128.2**, Uvicorn **0.48.0**,
httpx **0.28.1**, pytest **9.0.2**, dependencias ya presentes en `.venv`.

### Resultados ejecutados en esta tarea

Primera ejecución de TODA la batería existente, antes de los archivos nuevos:
**459 passed, 1 failed, 1 skipped, 26 subtests passed**, 57.78 s. El fallo fue
`test_import_exercises.py::LocalGitImportTests::test_unpublished_unit_and_symlinked_source_are_rejected`:
Windows devolvió **WinError 1314**, sin privilegio para `Path.symlink_to` en una
fuente curricular temporal. No es una prueba aprobada; no se cambió el test ni
la configuración de seguridad de Windows para ocultarlo. La omisión existente
es la prueba de enlaces de `test_actualizar.py`, que sí contempla esa limitación.

Última batería, con los archivos finales de la demo y excluyendo expresamente
SOLO ese caso que necesita privilegio del sistema:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
.\.venv\Scripts\python.exe -X dev -m pytest -q -p no:cacheprovider -o faulthandler_timeout=40 -W error::ResourceWarning -W error::pytest.PytestUnraisableExceptionWarning --deselect=test_import_exercises.py::LocalGitImportTests::test_unpublished_unit_and_symlinked_source_are_rejected
```

**630 passed, 1 skipped, 1 deselected, 26 subtests passed**, 61.55 s.
No se presenta como una pasada íntegra sin excepciones. Quedó un aviso de
obsolescencia Starlette/AnyIO sobre `BlockingPortal`; ningún ResourceWarning ni
excepción de limpieza ignorada en la pasada final.

Pruebas enfocadas finales de demo, ejecutadas mediante el wrapper PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Demo-Web.ps1 -Accion Pruebas
```

**171 passed**, 6.64 s: 119 del listener/recursos, 49 de PKI y 3 de transporte y
procesos. Se verificó whitelist literal, métodos, traversal, Host, forwarding,
cuerpos/cabeceras, límites, ausencia de imports de negocio/SQLite, CSP/no-store,
ausencia de referencias externas y service workers, challenge/ejecución/petición,
ACL de claves, SAN exacto, cadena canónica y huellas DER/PEM diferenciadas.

Las pruebas TLS usan sockets reales y verifican autoridad y nombre; rechazan CA
ajena, nombre incorrecto, otros DNS, descendientes e IP de ambas familias.
Hay controles causales: raíz con la misma identidad pero sin NameConstraints,
manteniendo la intermedia restringida; siguen rechazándose nombres/IP ajenos.
Al retirar ambas restricciones en certificados exclusivamente temporales, esos
controles aceptan los nombres; así se verifica la causa del rechazo. No equivale
a una ejecución del Chrome Android real.

Se comprobó reinicio con otro run_id, cierre del árbol del proceso propio y un
listener ajeno que sigue disponible; un puerto ya ocupado hace fallar el arranque
sin detener su propietario. Se corrigió durante QA el cierre del launcher Python
de Windows para que las pruebas detengan también su hijo; la operación normal
documentada es primer plano y Ctrl+C. No hay servicios ni tareas nuevos.

Prueba adicional FINAL con material persistente propio separado:
`D:\Projects\ServerTec\demo-web-20261019`, cadena raíz → intermedia → hoja,
listener real **127.0.0.1:443**, SNI **learngraphicsprogramming.dynamics**.
Se ejecutó `Demo-Web.ps1 -Accion Comprobar`, con cadena/nombre estrictos y sin
hosts, proxies ni omisión de errores de certificado:

- Menú y CSS/JS: 200 con recursos locales y no-store.
- Dos respuestas de estado frescas, eco correcto y request_id diferentes.
- Archivos privados, docs y negocio: 404; nombre TLS incorrecto: rechazado.
- run_id: `1fc9532ea881be2ea6e74aaa1c51b9d4`.
- Hora UTC de respuesta: `2026-10-19T06:06:32.846537Z`.
- Al detener el árbol propio: **cero listeners TCP443**, confirmado por Windows.

La clave de raíz e intermedia del material final no se conservó (`--one-shot`),
solo la clave de ejecución protegida por ACL. No hay claves nuevas dentro de Git.
No se instalaron autoridades de confianza. La huella SHA-256 del certificado
raíz DER es `dc4823f93b922cb013b98f183d9d09bc2aac19cf6c036caaace71b33f2d9501e`.
La hoja y la intermedia caducan `2026-10-26T05:59:59Z`.

También se ejecutaron:

- `ServerTec.ps1 -Accion AutoPrueba`: **9/9**, HTTPS/SQLite/proceso reales con estado
  temporal eliminado; arranque original y reglas QA históricas preservados.
- `Probar-Resumen-Red.ps1`: **9/9**, resumen sin consultar adaptadores.
- `python -m py_compile demo_web.py demo_pki.py demo_check.py`: correcto.
- `git diff --check`: correcto; HEAD y rama sin cambios.

No se inicializó ni abrió estado real: las rutas D, E y LOCALAPPDATA documentadas
de `state` se comprobaron ausentes. No se copiaron SQLite abiertas ni se tocaron
claves/certificados anteriores. Se comprobó al cierre: **0 reglas firewall demo**,
**sin entrada hosts demo**, **sin proceso demo ni listener443 de esta entrega**.

### Límites y pendientes explícitos

**Funciona localmente** por transporte TLS y pruebas; **software preparado para
prueba externa**, pero sin exposición activada; **confirmado desde otra red: NO**.
No se atribuyen a esta ejecución las antiguas «461 pruebas» como si fueran la
pasada de Windows actual; los resultados anteriores se conservan debajo.

Solo lectura de red: IPv4 privada 198.51.100.10, IPv6 global candidata, rutas de
ambas familias y TCP443 disponible. Windows perfil Public, entrada predeterminada
Block, sin regla específica de la demo. WAN IPv4/CGNAT, reglas/router TCP443 y
compatibilidad de la red externa siguen sin determinar. HTTP de solo lectura a
la puerta de enlace devolvió 400; no se autenticó ni cambió el router.

Chrome instalado: **155.0.8059.84**. Registro sin políticas relevantes de
certificados/DNS/HTTPS encontradas; política efectiva, importación de confianza,
validación TLS y ejecución visual/JavaScript en Chrome **no comprobadas**.
El control automático de interfaz detuvo la inspección al no determinar la URL
con suficiente confianza. La retirada de la carpeta de perfil temporal se rechazó
con «blocked by policy», sin motivo más concreto. Chrome se cerró; no se intentó
sortear esos controles. Quedan el perfil cerrado sin CA importada y la identidad
inicial QA no confiada, descritos en DEMO-WEB.md; no hay servicios activos.

El usuario confirmó Windows y Android externos con Chrome. Windows tiene receta
puntual de hosts y perfil dedicado, pendiente de autorización. Android requiere
concretar versión y una asociación local de nombre sin root; personalDNSfilter
se investigó como candidato local, **no se instaló/configuró ni probó**. Instalar
una CA Android afectaría el usuario/perfil Android, no exclusivamente Chrome;
se explicó ese alcance y no se solicitó ni aplicó instalación silenciosa.
La cadena intermedia restringida conserva las restricciones durante su validación,
sin presentar el comportamiento OpenSSL como aceptación del Chrome del teléfono.

No se abrieron puertos externos, ni se modificaron firewall/router/hosts/DNS/
confianza. No hubo servicios externos para servir el menú, CA comercial, túnel,
hosting ni nueva cuenta. No se usó Honor/ADB ni se migró Android/currículo. No se
afirma seguridad o disponibilidad de producción. Comandos, cambios concretos a
autorizar, distribución del certificado, clientes y reversión: [DEMO-WEB.md](DEMO-WEB.md).

## Evaluaciones autorizadas y recibos atómicos

2026-10-19 UTC. Base remota revisada:
`97941a5356e9e27c2cd10fb23a3a8daf800b06b6`, ServerTec/main.
Entorno temporal Linux, **Python 3.13.16**, SQLite **3.53.1**, con las mismas
versiones directas fijadas en requirements-test.txt. No hay dependencias nuevas.

Comando completo ejecutado:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -X dev -m pytest -q \
  -o faulthandler_timeout=40 -W error::ResourceWarning \
  -W error::pytest.PytestUnraisableExceptionWarning
```

Resultado: **461 pruebas aprobadas y 26 subpruebas aprobadas, cero fallos,
cero errores y cero omisiones**, en 34,64 segundos. Incluye la batería histórica
completa. El informe JUnit cuenta 487 casos porque suma las 26 subpruebas.

| Pruebas | Aprobadas |
|---|---:|
| Servicio: transacciones, recibos, corazones y fusiones | 72 nuevas |
| API: cuerpos, autoridad, errores y HTTPS real | 26 nuevas |
| Catálogo y evaluadores | 23 nuevas |
| Importador curricular | 16 nuevas |
| **Total de pruebas nuevas** | **137** |
| Pruebas históricas | 324 |
| **Total principal** | **461** |

Se ejecutaron dos terminaciones reales de procesos, antes y después del commit,
además de fallos SQLite en la creación del intento, inserción del resultado y
confirmación del recibo. Se comprobó reintento tras reinicio, catálogo retirado y
fusión; dos errores concurrentes con un corazón; A → B → A; protección del UUID
pendiente; cero corazones sin revelar corrección; datos privados separados;
sesiones revocadas y dispositivo no aceptado; deuda mayor que capacidad y reloj
atrasado. Los errores de almacenamiento no devuelven una evaluación confirmada.

La prueba HTTPS nueva usó sockets, certificados, scrypt y dos procesos Uvicorn
reales: el segundo recuperó la sesión y el recibo guardados sin volver a cobrar.
Se verificó persistencia en SQLite antes de considerar confirmada la respuesta,
integridad de la base y ausencia de secretos en el log temporal. La autoprueba
histórica de HTTPS también pasó sus **9/9** comprobaciones dentro de la batería.

Catálogo publicado de esta etapa: **364 ejercicios** en 33 archivos de lección
del commit Android `621f35c5565b1f02c39576a70f657b929f1970b4`, leído sin editar.
Se verificaron los 33 hashes Git de las fuentes, la reproducción exacta de catálogo
y cobertura, y 364 respuestas aceptadas tomadas de esos JSON. El informe enumera
los 36 bloques interactivos no instalados; no se presentan como evaluables.
La revisión independiente corrigió y comprobó dos diferencias Java/Python antes
de esta ejecución: redondeo DECIMAL64 en el límite de finitud y dígitos astrales.

La única advertencia fue una obsolescencia de BlockingPortal en Starlette/AnyIO;
no hubo ResourceWarning ni excepciones de limpieza ignoradas. Las dependencias
fijadas no se cambiaron para ocultar esa advertencia.

No se ejecutó Windows/PowerShell, Honor, LDPlayer, Google/Billing reales ni
acceso público/carga de producción. No se modificó el checkout Android ni el
estado real de la PC. La app todavía no llama a este endpoint y la ampliación
del catálogo sigue pendiente. Contrato y límites: EVALUACIONES.md.

## Validación de la primera entrega

2026-10-17. Ejecución local en entorno aislado Linux, Python 3.13.5.

Comando: `python -m pytest -q -p no:cacheprovider`.

Resultado inicial: **24 pruebas aprobadas**. Incluye una prueba de HTTPS con sockets reales, Uvicorn real, cadena de certificados privada y SQLite real. Todas las claves utilizadas en las pruebas se generan temporalmente; ninguna se entrega como credencial.

Se comprobó: recuperación horaria, límite de saldo, reloj atrasado, persistencia al reabrir DB, separación de cuentas/rutas, concurrencia con el mismo UUID, reutilización incorrecta de UUID, recibos de saldo cero, copia de WAL mediante backup, límites de petición, rechazo de datos extra (Premium/saldo falsos), SQL malicioso, autenticación obligatoria, ausencia de docs abiertas, credencial de pruebas restringida a loopback, no confiar en X-Forwarded-For, verificación RS256 real con claves temporales, rechazo de emisor/audiencia/proveedor/caducidad incorrectos y algoritmo none, rechazo TLS de nombre incorrecto y CA no confiable, ausencia del token en logs.

No comprobado aún: scripts PowerShell en Windows, acceso desde Honor/LDPlayer, Telmex entrante, Google/Firebase reales, Google Play Billing, disponibilidad 24/7, renovación de direcciones/certificados y capacidad a gran escala. No se realizó una auditoría externa de seguridad ni de vulnerabilidades de dependencias.

## Etapa 02: privacidad del diagnóstico y autoprueba local

2026-10-17. Ejecución actual en Linux con Python 3.13.5, usando las mismas versiones directas de dependencias de la primera entrega.

* `python -m pytest -q -p no:cacheprovider`: **40 pruebas aprobadas** (las 24 anteriores más 16 nuevas). Última ejecución: 7,22 s.
* `python autoprueba.py`: **9/9 comprobaciones aprobadas** con sockets HTTPS, certificados, proceso Uvicorn y SQLite reales. Proceso hijo detenido y estado temporal retirado al terminar.
* `python -m compileall -q . -x '/\.git/'`: sin errores de sintaxis Python.

Las nuevas pruebas cubren: autoprueba aislada sin abrir datos reales; rechazo de CA/nombre incorrectos; contexto TLS que mantiene verificación obligatoria y no exporta claves mediante SSLKEYLOGFILE; cierre exclusivo del proceso creado; limpieza ante fallos; actualización con hashes; conservación de archivos ajenos, .venv y datos; rechazo de cambios locales; rutas relativas/absolutas maliciosas; archivos privados en paquetes; enlaces simbólicos; reversión tras un fallo de escritura.

También se añadieron **9 comprobaciones PowerShell** del resumen recortado, sin dependencia de Pester. **No se ejecutaron aquí**, porque este entorno no incluye PowerShell. Se ejecutarán en Windows mediante `Preparar` o `Pruebas`. No deben confundirse con las 9 comprobaciones HTTPS de la autoprueba, que sí se ejecutaron.

El motor `servertec.py`, el aprovisionamiento `manage.py`, las dependencias, Android y el contrato de corazones/progreso no cambiaron en esta etapa. Sigue pendiente comprobar Windows 11/PowerShell 5.1 reales, Honor/LDPlayer, IPv4 WAN y conexiones entrantes, Google real y el descubrimiento de direcciones públicas cambiantes. No se abrieron puertos, no se instaló ningún certificado en el sistema y no se contrató ningún servicio.

## Paso 1 tras la planificación: cierre SQLite y datos separados del código

Base revisada: `8dc2682556be113096cd9a0fcd2ca7c4d2c20728`. El usuario notificó
un WinError 32 sobre `servertec.db` al retirar el directorio QA. Se encontró una
conexión abierta con `with sqlite3.connect(...)`: ese contexto gestiona transacciones,
pero no cierra la conexión. Ahora todas las comprobaciones de persistencia comparten
una conexión que se cierra explícitamente con `contextlib.closing` antes de limpiar.
No se alargaron los reintentos para ocultar el defecto.

Validación ejecutada en este paso, Linux / Python 3.13.5:

* Las nuevas regresiones, reteniendo las conexiones para que el recolector no oculte
  fugas, fallaron en el código anterior al terminar correctamente y al forzar un error
  durante la comprobación de ajustes. El cierre durante otra excepción ya funcionaba.
* `python -X dev -m pytest test_autoprueba.py test_sqlite_cleanup.py test_runtime_paths.py -q -p no:cacheprovider -W error::ResourceWarning`:
  **20 pruebas dirigidas aprobadas**. No es una nueva ejecución de toda la batería.
* `python autoprueba.py`: **9/9**, con HTTPS real, SQLite real y proceso hijo real.
* Compilación sintáctica de los módulos Python revisados: correcta.

Las rutas Windows se comprueban mediante pruebas de selección de plataforma y
comprobaciones estáticas de los scripts. **No se ejecutó PowerShell ni Windows aquí**.
Falta repetir `Pruebas` y `AutoPrueba` en el Windows del usuario con esta versión.
El entorno emitió un aviso de configuración del plugin pytest-asyncio; no hubo errores
por conexiones SQLite sin cerrar en las pruebas dirigidas.

Configuración de almacenamiento: código en `E:\PersonalFiles\Projects\ServerTec`;
estado en `D:\Projects\ServerTec\state`, respaldos en `state\backups` e informes
en `D:\Projects\ServerTec\reports`. `Rutas` informa sin escribir.
`Inicializar` comprueba el destino antes de crear directorios o modificar permisos y
se detiene si detecta datos anteriores en LOCALAPPDATA, en lugar de crear nuevas claves
y una segunda identidad de servidor silenciosamente. No se migraron datos de la PC.

Este paso no modifica `servertec.py`, el esquema SQLite, las reglas de corazones,
la API, dependencias, Android, Honor, LDPlayer ni la publicación en Google Play.
Los endpoints heredados de ajustes continúan presentes; su comprobación QA no activa
sincronización en Android ni cambia la decisión de mantener allí los ajustes locales.

## Paso 2: motor de referencia para recuperación y cartera offline

Base remota: `1b3c22a3de2ca9b5f23b401ce2f4605233f688f9`.
**Confirmación recibida del usuario en Windows para esa base:** 84 pruebas
aprobadas, 1 omitida y 1 aviso de deprecación; autoprueba HTTPS 9/9.

Se añaden `offline_hearts.py` y `test_offline_hearts.py`. Son un modelo ejecutable
Python y pruebas para fijar las reglas del futuro cliente Android, **no código
Kotlin ya integrado ni una nueva API de sincronización**. El servicio no importa
este módulo; no se modifican `servertec.py`, las tablas de producción, dependencias,
rutas D/E, ajustes ni Premium. Todo el almacenamiento nuevo de las pruebas es temporal.

El motor calcula la recuperación bajo demanda, incluso desde saldo cero sin red,
con los máximos existentes de 8/12 y sin acumular tiempo extra al estar lleno.
Usa muestras monotónicas del mismo arranque; si cambia el marcador de arranque,
usará una diferencia positiva del reloj civil, marcada como estimación no verificada.
Una hora manipulada tras reiniciar no queda mágicamente validada: esa concesión
aceptada en la planificación permanece visible. Un contador monotónico que retrocede
no acredita tiempo dos veces. El marcador de arranque aún debe obtenerse y probarse
en el adaptador Android; no basta con comparar si el contador actual es menor.

La cartera separada guarda consumo y recibo pendiente en una transacción antes de
retornar. Repetir el mismo UUID no vuelve a cobrar; un recibo antiguo no se aplica
como saldo actual. Las consultas de visualización no escriben ni generan envíos.
Un estado local ausente exige restauración verificada, no crea vidas automáticamente.
La función de inicialización requiere esa verificación por parte del futuro adaptador;
el modelo no autentica cuentas ni acredita por sí solo respuestas del servidor.

Validación ejecutada aquí: Linux / Python 3.13.5 / pytest 9.0.2.

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -X dev -m pytest test_offline_hearts.py -q -p no:cacheprovider -W error::ResourceWarning
```

**65 pruebas nuevas aprobadas.** Incluyen límites temporales, conservación de la
fracción de recarga, arranque nuevo con uptime mayor que el anterior, reloj adelantado
y atrasado, recarga offline desde cero, reapertura de SQLite, datos borrados o corruptos,
reintentos concurrentes, separación de cuentas/rutas, rechazo de bases ajenas,
fallo transaccional y salida abrupta REAL de un proceso entre consumo y recibo.
Dos secuencias deterministas de 1.000 operaciones se contrastan con un cálculo
independiente. Se comprueba el cierre explícito de todas las conexiones reteniendo
referencias para que el recolector no oculte fugas.

**No se ejecutó de nuevo aquí toda la batería del servidor ni Windows/PowerShell,
Honor o LDPlayer.** La batería `Pruebas` del usuario recogerá automáticamente los
nuevos tests después del Pull. La autoprueba HTTPS existente no cambia.

Antes de integrar: revisión independiente de Codex sobre conciliación de recargas
locales y recibos pendientes. Aún no hay transporte, confirmación/borrado de pendientes,
restauración tras pérdida de datos ni resolución entre dispositivos. Enviar estos
recibos a `/v1/hearts/debits` tal como está no demuestra una conciliación correcta.
Los pendientes jamás recibidos no pueden darse por conocidos por ServerTec. No se
promete que este motor por sí solo resuelva ese caso ni que detecte toda manipulación.

Referencias técnicas consultadas para este paso:
* https://developer.android.com/reference/kotlin/android/os/SystemClock
* https://developer.android.com/reference/android/provider/Settings.Global#BOOT_COUNT
* https://docs.python.org/3.13/library/sqlite3.html#how-to-use-the-connection-context-manager


## 2026-10-18 — Autenticación v2 y saldo ligado a la cuenta

Base de esta tanda: d466f086ce732aafaafb6bbf4f66af207402e596, ServerTec/main.

Se añaden accounts.py, account_ledger.py y sus pruebas; se integra el contrato HTTP
v2 en servertec.py y la emisión local de invitaciones en manage.py/ServerTec.ps1.
AUTENTICACION.md describe el contrato y sus límites. Las tablas heredadas se
conservan. No se modifican dependencias, rutas D/E ni el repositorio Android.

Validación ejecutada sobre este cambio: Linux, Python 3.13.16, pytest 9.0.2 y las
versiones fijadas de requirements.txt.

```text
python -X dev -m pytest -q -p no:cacheprovider \
    -W error::ResourceWarning -W error::pytest.PytestUnraisableExceptionWarning
265 passed, 1 warning in 19.89s

python autoprueba.py
Resultado: 9/9
```

El aviso restante procede de la compatibilidad Starlette/AnyIO:
anyio.abc.BlockingPortal es un alias deprecado. No se cambiaron las versiones de
dependencias para ocultarlo. Se cerraron cinco conexiones SQLite que las pruebas
heredadas dejaban abiertas; la pasada final trata ResourceWarning y excepciones
no capturables del recolector como errores, sin avisos de conexiones.

Cobertura nueva:

- 52 pruebas del núcleo de cuentas: unicidad y concurrencia, invitación de un uso,
  caducidad mientras espera un escritor SQLite, rollback de inscripción,
  scrypt real y formato fijo, sesiones sólo por hash, recuperación sin autologin,
  revocación, límites persistentes y carreras de cambio de credenciales.
- 42 pruebas del saldo canónico: alta de ambas rutas una vez, reapertura, ausencia
  de estado sin grants, recarga lazy, reloj atrasado, suma de deuda de dispositivos
  sin duplicar snapshots, deuda superior a capacidad, transacciones, copia de
  progreso y cierre de conexiones.
- 21 pruebas de integración HTTP: registro, login, recuperación, cambio y logout,
  cuenta deshabilitada, retiro v1 en producción, cabeceras falsificadas, error
  de almacenamiento, saldo ausente, Firebase firmado con claves temporales,
  proyecto/proveedor/fechas incorrectos y migración de UID heredado.
- La prueba HTTPS existente se amplió con registro v2 y scrypt real, lectura de
  saldo, identidad y logout contra Uvicorn mediante sockets y certificados
  reales. Verifica que contraseña, invitación, sesión y recuperación no aparezcan
  en el archivo de logs.

Una revisión independiente del código identificó y permitió corregir la vía de
acceso heredada v1 tras deshabilitar una cuenta y la caducidad de invitación
comprobada antes de esperar el bloqueo. Revalidó además secretos en SQLite,
revocación de sesiones y la carrera entre login y cambio de credential_version.

La autoprueba 9/9 conserva su contrato QA histórico; no representa nueve pruebas
del evaluador v2. Ese evaluador aún no existe. Este paso tampoco verifica Google
real, revocación remota Firebase, Windows/PowerShell, Honor, LDPlayer, acceso
público ni carga de producción. No se ha alterado estado real en la PC del usuario.

El diseño vigente sustituye la autorización de comprobaciones offline del modelo
anterior: el futuro Android esperará una evaluación online confirmada. El módulo
offline_hearts.py permanece como experimento QA sin importar desde el servicio.

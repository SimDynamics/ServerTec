# ServerTec / servidor independiente de LearnGraphicsProgramming

Servidor propio para LearnGraphicsProgramming. Código aislado de Android. **No está conectado todavía a la app ni habilitado para Internet o Google Play.** No modifica APK, voces, Enter, progreso local, router, DNS ni firewall.

## Ubicación y alcance

**Repositorio actual:** `SimDynamics/ServerTec` (privado, rama `main`), independiente de `SimDynamics/LearnGraphicsProgramming`. **Copia local:** `E:\PersonalFiles\Projects\ServerTec`. La migración por Git y la retirada de `server/ServerTec` del árbol `main` de la app ya se completaron. El repositorio público de recursos no participa. Claves privadas, certificados y SQLite permanecen fuera del código.

Esta implementación usa Python 3.13+, FastAPI, Uvicorn, SQLite, cryptography y PyJWT. Son herramientas ejecutadas en tu equipo, sin suscripción de hosting ni cuota de operaciones de un proveedor. **No es el ejemplo previo en ASP.NET/C#: es una implementación Python independiente que se ha podido ejecutar y probar en este entorno.** No es un servicio de FastAPI alojado. La descarga de dependencias usa el registro de paquetes; el servidor no depende de ese registro después de instalarlas.

No se instala nada automáticamente con el diagnóstico. No hay Docker Desktop, túneles, dominios, plataformas de despliegue ni GitHub Actions nuevos. GitHub solo conserva código fuente.

## Datos en D y código en E

El código Git permanece en `E:\PersonalFiles\Projects\ServerTec`. El almacenamiento persistente es `D:\Projects\ServerTec`:

* `state`: SQLite, certificados, claves, configuración y credencial de pruebas.
* `state\backups`: respaldos privados de SQLite y su clave HMAC.
* `reports`: diagnósticos privados de red.

`ServerTec.ps1 -Accion Rutas` muestra estas ubicaciones sin crear ni mover archivos. `manage.py` usa la misma ruta de estado por defecto en Windows; `--state` continúa disponible para pruebas aisladas. La autoprueba usa solo un directorio temporal desechable del sistema, no abre los datos de D.

**No se trasladan datos antiguos automáticamente.** Si `Inicializar` detecta estado anterior en `%LOCALAPPDATA%\ServerTec\state`, se detiene antes de crear otro estado o generar nuevas claves. Si D no está disponible, no se sustituye silenciosamente por C ni por el repositorio. GitHub Desktop recibe únicamente código; no copia bases de datos ni secretos.

## Primera ejecución en Windows

Tras clonar el repositorio privado en `E:\PersonalFiles\Projects\ServerTec`, **las actualizaciones posteriores llegan por Git, no por ZIP**. El usuario recibe las actualizaciones mediante Fetch/Pull en GitHub Desktop, seleccionando ServerTec y main; conservar cualquier cambio local propio. Abrir PowerShell normal, sin administrador:

```powershell
Set-Location -LiteralPath 'E:\PersonalFiles\Projects\ServerTec'
powershell -NoProfile -ExecutionPolicy Bypass -File .\ServerTec.ps1 -Accion Diagnostico
```

`Bypass` solo afecta a ese proceso, no cambia permanentemente la política de Windows. El diagnóstico lee las direcciones, prefijos reales, rutas y disponibilidad de Python/ADB. No escanea Internet. El informe completo queda fuera de Git, en `D:\Projects\ServerTec\reports`. Compartir solo su resumen.

Después, cuando esté disponible Python 3.13 o posterior, **validar primero la copia de prueba aislada**:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\ServerTec.ps1 -Accion Preparar
powershell -NoProfile -ExecutionPolicy Bypass -File .\ServerTec.ps1 -Accion AutoPrueba
```

**Solo después de aprobar la autoprueba**, si se desea inicializar un estado local persistente de desarrollo, utilizar:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\ServerTec.ps1 -Accion Inicializar
powershell -NoProfile -ExecutionPolicy Bypass -File .\ServerTec.ps1 -Accion Iniciar
```

`Preparar` crea un entorno `.venv`, instala las versiones de `requirements-test.txt` y ejecuta las pruebas. No desinstala versiones globales. `Inicializar` limita permisos de la nueva carpeta de estado mediante `icacls` y pide una frase privada para cifrar la clave de la autoridad. **No compartir esa frase ni los archivos de estado.** Conservarla en un lugar seguro. No hay contraseña universal en el código.

En otra ventana de PowerShell:

```powershell
Set-Location -LiteralPath 'E:\PersonalFiles\Projects\ServerTec'
powershell -NoProfile -ExecutionPolicy Bypass -File .\ServerTec.ps1 -Accion Verificar
```

Debe confirmar HTTPS con validación de certificado y nombre/IP. El servidor escucha únicamente en `127.0.0.1:8443`. Para detenerlo: Ctrl+C. No se instala todavía como servicio permanente.

## Autenticación e historiales compartidos: estado actual

La API v2 incorpora usuario y contraseña sin correo, Google/Firebase, sesiones
revocables e historiales de consumo gratuito compartidos entre cuentas y dispositivos.
[HISTORIALES.md](HISTORIALES.md) documenta el contrato vigente de corazones y
confirmaciones. Sustituye las reglas por cuenta y sin ANDROID_ID descritas en
[AUTENTICACION.md](AUTENTICACION.md); el resto del contrato de autenticación se conserva.

- El servidor genera el identificador interno. El nombre de usuario es único sin
  distinguir mayúsculas. Contraseñas, sesiones, invitaciones y códigos privados
  se guardan como hashes; nunca se admite un UID, saldo o Premium elegido por Android.
- Las cuentas nuevas necesitan una invitación privada de un uso durante esta
  fase de pruebas. Google también exige invitación para cuentas nuevas. Los UID
  Google con datos anteriores a la migración pueden recuperar su identidad
  mediante un token verificado. No se vinculan dos cuentas por correo o nombre.
- Cada grupo comparte un único saldo por ruta: 8 corazones en Programación y 12
  en Matemáticas/Física, con una recuperación por hora calculada al consultar.
  Cinco cuentas sobre un mismo dispositivo reconocido no producen cinco recargas.
  No hay temporizadores por usuario ni servicios nuevos con cuotas comerciales.
- Un dispositivo nuevo de una cuenta conocida requiere confirmación de un uso.
  Cancelar no une grupos ni modifica corazones. La confirmación caduca y queda
  vinculada a la sesión, cuenta, dispositivo y grupos afectados.
- Unir historiales suma sólo deudas independientes, conserva la raíz más antigua
  y sus alias; nunca concede otro saldo ni comparte credenciales, progreso o Premium.
- El alta prepara un grupo dentro de la transacción de cuenta e invitación.
  No puede usarse desde un dispositivo sin asociarlo. Un alta nueva en un
  dispositivo conocido se une a su grupo y no añade corazones disponibles.
- La migración copia una sola vez los saldos canónicos anteriores; no vuelve
  a sumar sus snapshots por dispositivo. Las tablas anteriores quedan como archivo.
  Un estado faltante o dañado exige reparación; no se repone con vidas nuevas.
- El acceso local incluye un código privado de recuperación mostrado una vez.
  Recuperar la contraseña conserva identidad y saldo, revoca todas las sesiones
  y exige iniciar sesión de nuevo. También existen cierre de sesión y
  deshabilitación administrativa local.
- HTTPS, validación de certificados, límites de cuerpo, frecuencia y concurrencia
  continúan activos. Las comprobaciones costosas de contraseña se limitan a una
  simultánea por proceso; consultar con una sesión sólo requiere su validación en SQLite.

**La evaluación de respuestas todavía no está implementada.** La API v2 permite
autenticar, consultar el saldo y leer progreso preservado. No hay una ruta pública
v2 para descontar corazones ni para declarar una respuesta correcta.
La primitiva interna de débito exige una transacción y está reservada para el
futuro evaluador; por sí sola no aporta validación ni idempotencia de intentos.

### Contrato vigente y retirada del prototipo

| Método | Ruta | Función |
|---|---|---|
| GET | `/health` | Estado mínimo |
| POST | `/v2/auth/register` | Usuario, contraseña e invitación |
| POST | `/v2/auth/login` | Iniciar sesión local |
| POST | `/v2/auth/google` | Intercambiar ID token Firebase de Google verificado |
| POST | `/v2/auth/recover` | Recuperar con código privado y contraseña nueva |
| POST | `/v2/auth/password` | Cambiar contraseña con sesión y contraseña actual |
| POST | `/v2/auth/logout` | Revocar la sesión actual |
| GET | `/v2/auth/me` | Identidad de la sesión |
| POST | `/v2/devices/prepare` | Asociar primer dispositivo nuevo o preparar la advertencia |
| POST | `/v2/devices/confirm` | Aceptar una confirmación válida de un solo uso |
| POST | `/v2/devices/cancel` | Cancelar sin unir historiales ni cambiar corazones |
| GET | `/v2/hearts/{route}` | Saldo compartido, grupo vigente y próxima recuperación |
| GET | `/v2/progress` | Progreso de la identidad canónica |

Las rutas protegidas v2 requieren `Authorization: Bearer <sesión>`.
Las rutas de dispositivos y corazones requieren además `X-Android-Id`; las de
identidad y progreso no dependen de esa asociación. No aceptan tokens QA como
cuentas reales. Todas las rutas
`/v1/*` quedan retiradas con HTTP 410 cuando `testing=false`.
Sólo siguen disponibles en el modo QA con credencial aleatoria y origen loopback,
para conservar las pruebas históricas. Sus descuentos y completados declarados
por el cliente no forman parte del contrato final.

La copia consistente `-Accion Respaldo` incluye las nuevas tablas de cuentas,
sesiones y saldos al respaldar SQLite. Conserva además la clave HMAC heredada
cuando existe. Este respaldo en el mismo disco todavía no tolera una avería del
equipo; restaurar una copia antigua puede retroceder datos, sesiones y consumos.
Para esta fase, detén el servidor antes del respaldo y de actualizar o restaurar.
Nunca ejecutes versiones antiguas y nuevas simultáneamente sobre el mismo estado.
La clave HMAC queda fijada al historial: perderla o cambiarla produce un error,
no nuevos dispositivos con corazones nuevos.

## IPv6 dinámica: bloqueo de publicación aún abierto

La prueba del usuario mostró dos prefijos diferentes después de reiniciar el router. No se fija la dirección desactivando DHCP de Windows. **Este proyecto no promete descubrimiento automático de una IP nueva sin un punto de referencia estable.** Guardar la IP nueva en el mismo servidor que ya no se encuentra no resuelve el problema.

Para pruebas iniciales: loopback y, en la siguiente fase, ADB con un cliente de pruebas que confíe exclusivamente en nuestra autoridad. Para red local/remota: dirección actual comunicada explícitamente y certificado con su IP en SAN. Cambiar de IP requiere actualizar la dirección en el cliente y emitir un certificado válido para la nueva IP, conservando la autoridad. No se desactiva la verificación de nombre.

No se introducen DNS dinámicos, dominio, túnel, proxy ni un repositorio público de descubrimiento. La reconexión automática pública queda pendiente de una decisión que satisfaga las restricciones. También falta comprobar IPv4 WAN/CGNAT, firewall del router y acceso desde una red externa; una IPv6 global local no demuestra accesibilidad ni compatibilidad con clientes solo IPv4.

## Git y secretos

Estado: `D:\Projects\ServerTec\state`. Contiene base de datos, token de pruebas, configuración, certificado y claves. El servidor rechaza ubicarlo dentro del código. La CA privada queda cifrada; la clave de ejecución se protege mediante permisos locales y no se sirve por HTTP. El script no instala la CA como autoridad del sistema.

`.gitignore` es una protección adicional, no cifrado, y no borra secretos ya subidos. No mover bases o claves al repositorio al publicar. El certificado público de la autoridad podrá incorporarse al cliente en la fase Android; la clave privada nunca.

## Próximos pasos del diseño autorizado

El diseño aceptado exige conexión para comprobar respuestas antes de mostrar el
resultado. ServerTec deberá evaluar contra reglas propias y confirmar intento,
resultado y descuento juntos, con idempotencia por intento. La respuesta incluirá
saldo y próxima recuperación para evitar una consulta adicional.

La app podrá leer, escuchar recursos instalados y preparar respuestas offline.
Una estimación local de recarga no autorizará evaluaciones ni modificará el
saldo del servidor. `offline_hearts.py` conserva el experimento anterior para QA;
no lo importa el servicio y su enfoque de recibos offline no debe activarse.
Las nuevas reglas sustituyen ese plan anterior.

Pendiente en ServerTec: catálogo y evaluador autoritativos, idempotencia completa
de evaluación, pruebas de interrupción y repetición, verificación de revocación
real Firebase, política pública de registro, respaldo externo y restauración,
auditoría de dependencias, carga y acceso remoto.

La integración Android es una fase posterior en su repositorio y rama autorizados.
Los ajustes permanecen locales; sólo el progreso curricular completado se prevé
sincronizar. No se integró todavía este contrato en Honor ni LDPlayer, ni se
cambió el control de descargas con datos móviles. Premium requiere su flujo de
compra y verificación independiente; esta entrega no concede Premium.

## Referencias técnicas

* https://fastapi.tiangolo.com/deployment/manually/
* https://uvicorn.dev/settings/
* https://docs.python.org/3.13/library/sqlite3.html
* https://firebase.google.com/docs/auth/admin/verify-id-tokens
* https://developer.android.com/privacy-and-security/security-config
* https://git-scm.com/docs/gitignore
* https://learn.microsoft.com/en-us/powershell/module/nettcpip/get-netipaddress

Las pruebas se ejecutan en Linux con Python 3.13; eso no equivale a Windows,
Honor o LDPlayer. `RESULTADOS.md` conserva los resultados anteriores y
`HISTORIALES.md` registra las comprobaciones específicas de esta etapa.

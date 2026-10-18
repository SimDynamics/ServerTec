# Autenticación v2 y saldo por cuenta

## Alcance de este paso

Implementación del servidor, en ServerTec/main. Ofrece registro con usuario y
contraseña sin correo, acceso alternativo con Google/Firebase, recuperación
local, sesiones, saldo canónico y lectura del progreso preservado.

El servidor continúa limitado a loopback por manage.py. No se ha conectado el
cliente Android ni abierto el router. Las evaluaciones de puzzles todavía no
existen en v2: falta verificar la solución, registrar el intento y confirmar el
descuento juntos antes de mostrar el resultado al estudiante.

## Identidad y registro

El identificador interno acct_ se genera en el servidor. No cambia al iniciar
sesión, recuperar la contraseña, borrar la app o usar otro dispositivo.

Un nombre acepta de 3 a 32 caracteres ASCII: letras, números y guion bajo.
Aresitos56 y aresitos56 comparten la misma clave de unicidad. El nombre no concede
privilegios ni se usa como identificador de otra cuenta.

La contraseña admite de 15 a 128 caracteres, hasta 512 bytes UTF-8. Se conserva
exactamente: no se recorta, no se convierte a minúsculas ni se trunca. Los hashes
usan scrypt con N=32768, r=8, p=3, sal aleatoria de 16 bytes, resultado de 32 bytes y
límite de memoria de 64 MiB. Es una configuración alternativa admitida por OWASP.
Los parámetros almacenados no pueden solicitar mayor costo. No se ha incorporado
todavía una lista de contraseñas comprometidas.

Durante esta fase, toda cuenta NUEVA, tanto local como Google, necesita una
invitación de un solo uso. Comprobar únicamente que un nombre está disponible no
impide crear múltiples cuentas. La invitación limita el alta durante QA; no es
una prueba de que cada persona tenga exactamente una cuenta.

La invitación, la cuenta, el vínculo Google cuando corresponde, los dos saldos y
la sesión inicial se confirman juntos. Un fallo revierte el alta y no consume
la invitación. La caducidad se comprueba después de adquirir el bloqueo SQLite.

## Recuperación sin correo y sesiones

El registro local devuelve un recovery_code privado una sola vez. El estudiante
debe conservarlo fuera de la instalación Android. El servidor sólo guarda su hash.

Recuperar requiere nombre, código y nueva contraseña. Conserva la identidad y
los datos, reemplaza el código, revoca todas las sesiones y exige iniciar sesión
normalmente. Si se pierde la respuesta de recuperación, la contraseña elegida
sigue permitiendo entrar; un cambio posterior de contraseña autenticado permite
obtener otro código. Perder contraseña y código no autoriza a recuperar la cuenta
sólo con su nombre.

Cambiar contraseña requiere sesión y contraseña actual. Revoca las sesiones
anteriores y devuelve una sesión y un código de recuperación nuevos. Logout
revoca la sesión actual. Disable-account es una operación administrativa local
que impide nuevos accesos y conserva saldo y progreso.

Las sesiones son valores aleatorios de 32 bytes con prefijo st1_. SQLite almacena
SHA-256 del valor completo. Se verifican caducidad, versión de credenciales y
estado de cuenta en cada operación protegida. Máximo: ocho sesiones por cuenta.

- Sesión local: caducidad absoluta de 30 días.
- Sesión Google: como máximo 15 minutos y nunca más que el ID token verificado.
- Recuperación, cambio de contraseña y deshabilitación invalidan sesiones
  anteriores dentro de la misma transacción que el cambio.
- La verificación de contraseña ocurre fuera de una transacción SQLite de
  escritura. Antes de emitir sesión se comprueba otra vez la versión de
  credenciales para cerrar carreras con recuperación o deshabilitación.

No se guardan contraseñas, sesiones, invitaciones ni códigos de recuperación en
claro en la base. Las respuestas que los entregan deben mantenerse privadas; no
copiarlas a Git, registros de depuración, capturas compartidas o reportes.

## Google y preservación de cuentas anteriores

Se verifica la firma RS256, proyecto, emisor, audiencia, fechas, sujeto y proveedor
google.com del ID token Firebase. El proyecto queda fijado en auth_meta; cambiarlo
requiere una migración explícita, no reinterpretar los mismos UID como otra
población. Las claves públicas se guardan temporalmente en memoria.

Al instalar el esquema de cuentas por primera vez se captura el conjunto de UID
con datos heredados. Un token Google verificado de ese conjunto puede migrar sin
invitación. Los registros creados por el prototipo después de esa captura no
habilitan esta excepción. El vínculo se confirma una vez y permanece estable.

Google y usuario/contraseña son alternativas de registro; esta entrega no vincula
una cuenta local existente con otra cuenta Google. No se fusionan cuentas por
correo, nombre visible o un identificador enviado por el teléfono.

**La revocación remota Firebase todavía no se consulta.** Un ID token vigente
podría intercambiarse de nuevo hasta que venza. Quince minutos limita una sesión
emitida, no toda esa ventana. La deshabilitación local sí invalida el acceso
posterior v2. La verificación con una cuenta Google real y revocación remota queda
pendiente antes de exposición pública.

## Corazones y migración

Los saldos se guardan por cuenta y ruta: 8 en programación y 12 en
matemáticas/física. Un identificador Android distinto no cambia esa clave.

Al registrar una cuenta nueva se crean ambas rutas. Leer o iniciar sesión nunca
concede un saldo inicial. Si falta cualquiera de las rutas después del alta, se
devuelve wallet_state_missing y se requiere reparar/restaurar los datos del
servidor: no se regalan corazones para ocultar la pérdida de estado.

La recuperación se calcula al recibir una consulta usando el reloj del servidor.
No hay tareas por usuario ni consultas periódicas obligatorias. Las contraseñas
sólo se verifican al entrar o cambiarlas; no se recalcula scrypt al consultar saldo.

Al migrar una cuenta anterior, por cada ruta:

1. Se toman los saldos por dispositivo, si existen. En ese caso se ignora el
   snapshot hearts que el prototipo ya había copiado al primer dispositivo.
2. Si no existen dispositivos para esa ruta, se toma el saldo heredado hearts.
3. Se calcula cada deuda usando su propio instante de referencia y el tiempo
   realmente transcurrido.
4. Se suman las deudas sin perdonar el exceso sobre la capacidad.
5. Se guardan el saldo canónico y las copias de progreso/ajustes heredados dentro
   de la transacción de alta. Las filas antiguas permanecen como archivo.

Ejemplo: dos dispositivos con cinco horas de deuda cada uno, con capacidad ocho,
producen diez horas de deuda. El saldo es cero y el primer corazón se recupera
en tres horas. Recortar esa deuda a ocho perdonaría dos horas.

Un reloj del servidor que retrocede no concede recuperación. No se promete
proteger frente a un administrador que manipule la base o restaure un respaldo
antiguo. El cliente nunca envía el tiempo usado para autorizar corazones.

## Contrato HTTP

Los cuerpos JSON son estrictos y rechazan propiedades adicionales. Las respuestas
de validación no incluyen el cuerpo rechazado. Se exige HTTPS y se envía no-store.

| Método y ruta | Cuerpo o credencial |
|---|---|
| POST /v2/auth/register | username, password, invitation |
| POST /v2/auth/login | username, password |
| POST /v2/auth/google | id_token; invitation para cuenta nueva |
| POST /v2/auth/recover | username, recovery_code, new_password |
| POST /v2/auth/password | sesión Bearer; current_password, new_password |
| POST /v2/auth/logout | sesión Bearer |
| GET /v2/auth/me | sesión Bearer |
| GET /v2/hearts/programming | sesión Bearer |
| GET /v2/hearts/math_physics | sesión Bearer |
| GET /v2/progress | sesión Bearer |

Registro/inicio de sesión devuelven account_id, access_token, token_type y
expires_at_ms. Las cuentas locales incluyen username; el registro incluye además
recovery_code. La recuperación devuelve require_login=true y no entrega sesión.

Todas las rutas v1 de datos personales están retiradas con HTTP 410 cuando
testing=false, incluido el descuento sin evaluación. En testing=true continúan
sólo con credencial QA y origen loopback para las pruebas históricas. Esa credencial
no da acceso a cuentas v2. No existen rutas HTTP de administración o de alta de
invitaciones. Tampoco hay POST v2 de descuento o de completados declarados por el
cliente; la futura evaluación deberá gobernar esos cambios.

## Costo y límites para QA

Los límites persisten en SQLite y se aplican antes de scrypt. El peer procede del
socket, no de X-Forwarded-For. IPv6 se agrupa por /64. La tabla acepta como máximo
4096 buckets; al llenarse rechaza trabajo nuevo, sin expulsar límites activos.

| Operación | Ventana | Global | Por IP | Por usuario/sujeto |
|---|---:|---:|---:|---:|
| Registro | 1 hora | 30 | 5 | 5 |
| Login/Google | 15 minutos | 120 | 40 | 10 |
| Recuperación/cambio | 1 hora | 60 | 10 | 5 |

Se permite un solo hash de contraseña simultáneo por proceso, sin cola. Saturación
devuelve 503 y el límite de intentos 429, con Retry-After. Estas cifras son una
configuración inicial de QA; no acreditan capacidad de producción ni miles de
usuarios. Los límites de login no se aplican a cada consulta autenticada de saldo.

## Administración en la PC

Después de Fetch/Pull en GitHub Desktop, seleccionar ServerTec/main y ejecutar
las pruebas sobre la copia actual. No volver a Inicializar un estado existente.

```powershell
Set-Location -LiteralPath 'E:\PersonalFiles\Projects\ServerTec'
powershell -NoProfile -ExecutionPolicy Bypass -File .\ServerTec.ps1 -Accion Pruebas
powershell -NoProfile -ExecutionPolicy Bypass -File .\ServerTec.ps1 -Accion AutoPrueba
```

Para emitir una invitación de QA desde el estado privado existente:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\ServerTec.ps1 -Accion Invitacion
```

La consola muestra un secreto de un uso, válido siete días. No incluir esa salida
al compartir resultados. El comando no lo envía a otra persona.

Para deshabilitar una identidad concreta, el operador usa localmente
manage.py disable-account --account-id seguido del identificador interno exacto.
El comando carga la configuración existente y usa el estado privado en D.

El respaldo SQLite incluye cuentas, sesiones, invitaciones y saldos nuevos. Debe
protegerse como un secreto. El respaldo aún requiere una copia externa y un
procedimiento de restauración comprobado.

## Qué falta para cumplir el flujo de evaluación completo

El siguiente módulo debe cargar reglas curriculares aprobadas en el servidor,
validar respuestas reales y guardar intento, resultado y descuento de forma
atómica e idempotente. La respuesta incluirá saldo y próxima recuperación.
Android deberá esperar esa confirmación antes de mostrar correcto/incorrecto.

Después se probarán respuesta perdida, reintento, cierre abrupto, borrado,
reinstalación y falta de conexión en la integración Android autorizada. La lectura,
narración instalada y preparación de respuestas pueden continuar offline; confirmar
una evaluación necesitará conexión. El control de descargas con datos móviles
existente pertenece a Android y no se cambia en esta fase.

## Referencias primarias de las decisiones de seguridad

- https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html
- https://docs.python.org/3.13/library/hashlib.html#hashlib.scrypt
- https://docs.python.org/3.13/library/secrets.html
- https://docs.python.org/3.13/library/sqlite3.html
- https://firebase.google.com/docs/auth/admin/verify-id-tokens
- https://firebase.google.com/docs/auth/admin/manage-sessions

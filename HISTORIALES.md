# Historial compartido de corazones: contrato del servidor

Este paso sustituye el saldo operativo por cuenta descrito en AUTENTICACION.md.
Se mantienen sus reglas de autenticación, invitaciones de QA y recuperación.
Solo cambia ServerTec/main; no se modifica Android, Premium ni datos de la PC.

## Qué queda implementado

Cada cuenta tiene una relación con un grupo de consumo. Cada dispositivo
reconocido tiene otra. Al aceptar una asociación se unen las raíces distintas:
todas las cuentas y dispositivos relacionados comparten un saldo por ruta,
con máximos de 8 en Programación y 12 en Matemáticas/Física y una recuperación
de un corazón por hora. Cinco cuentas en el mismo dispositivo no proporcionan
cinco depósitos de corazones ni cinco recuperaciones paralelas.

El grupo más antiguo permanece como raíz; los empates se resuelven por su ID.
Los grupos absorbidos permanecen como alias de un salto, incluso después de
varias uniones. Las sesiones existentes resuelven la raíz actual en cada operación.
La unión NO combina credenciales, correo, permisos, recuperación, progreso privado
ni derechos Premium. No ofrece una lista de cuentas de otras personas.

La lectura de identidad y progreso privado continúa requiriendo una sesión válida,
pero no la asociación del dispositivo para corazones. Cancelar una asociación
no cierra esa sesión ni afecta una compra. La app futura no debe confundir la
autorización de consumo gratuito con la autenticación o la licencia Premium.

## Dispositivo y privacidad

La cabecera X-Android-Id debe contener el identificador hexadecimal de 16 caracteres.
Se normalizan sus mayúsculas y se calcula un HMAC con un dominio propio. A diferencia
del prototipo v1, el digest no depende del usuario: reconoce el mismo identificador
entre cuentas. La base de datos no guarda el ANDROID_ID original.

Se reutiliza device-hmac.key, fuera del repositorio, con separación del uso heredado.
La base fija su huella criptográfica. Una clave perdida, dañada o cambiada causa
un error; el servidor no genera otra para aparentar que todos son dispositivos nuevos.
El digest del dispositivo tampoco se devuelve en la respuesta de consentimiento.

ANDROID_ID es una señal del cliente, no una prueba criptográfica del teléfono.
Otro perfil Android puede producir otro identificador; un cliente alterado puede
inventarlo. Una cuenta nueva junto con un ID no relacionado puede formar otro grupo.
Esta limitación permanece, como se aceptó en el encargo. No se incorporan Play
Integrity, Device Recall ni un proveedor externo de identificación.

## Flujo HTTP para el futuro cliente

Primero se autentica con los endpoints existentes: registro, login local o Google.
Después, para utilizar corazones, llama a:

| Método y ruta | Cuerpo | Cabeceras |
|---|---|---|
| POST /v2/devices/prepare | Vacío o {} | Authorization: Bearer sesión; X-Android-Id |
| POST /v2/devices/confirm | {"confirmation_token":"valor recibido"} | Las mismas sesión y dispositivo |
| POST /v2/devices/cancel | {"confirmation_token":"valor recibido"} | Las mismas sesión y dispositivo |
| GET /v2/hearts/programming | Ninguno | Sesión y dispositivo ya asociados |
| GET /v2/hearts/math_physics | Ninguno | Sesión y dispositivo ya asociados |

Los cuerpos son estrictos: no aceptan confirmed=true, saldo, UID o grupo elegido
por Android. Los tokens son secretos; no deben incluirse en URLs, logs ni informes.

PREPARE devuelve uno de estos estados:

- linked: la pareja cuenta/dispositivo ya existe o acaba de asociarse por primera
  vez a una cuenta realmente nueva. Incluye account_id, group_id y los saldos
  actuales de ambas rutas en hearts, sin otra petición obligatoria de saldo.
- confirmation_required: una cuenta conocida intenta utilizar un dispositivo
  que no tiene registrado personalmente. Incluye confirmation_token,
  expires_at_ms y los textos/versionado del aviso. No une grupos ni recupera saldo.

El primer dispositivo de una cuenta NUEVA se asocia sin advertencia. Si ese
identificador ya pertenece a otro historial, se incorpora al saldo existente;
no obtiene los corazones de un depósito adicional. Una cuenta antigua que use
por primera vez un dispositivo requiere consentimiento, aunque otra cuenta de
su grupo lo conozca. Esto evita asumir consentimiento personal por una relación
transitiva. La misma pareja ya aceptada no vuelve a pedirlo en cada apertura.

CONFIRM devuelve linked con el saldo actual. El aviso preparado dice:

> Vincular nuevo dispositivo
>
> Detectamos que estás intentando iniciar sesión con tu usuario o correo en un
> dispositivo que todavía no está registrado en tu historial.
>
> Si continúas, este dispositivo se añadirá a tu historial y compartirá los mismos
> corazones gratuitos con las cuentas y dispositivos vinculados. Si este dispositivo
> ya pertenece a otro historial de corazones, ambos historiales se unirán.
>
> ¿Deseas continuar?
>
> Sí, continuar / No, cancelar

El servidor entrega este aviso, pero su pantalla Android todavía no está integrada.
CANCEL devuelve cancelled y solo inutiliza esa confirmación. No modifica grupos,
saldos, recuperación, historial ni sesión. La pareja sin aceptar no puede consultar
ni usar el saldo gratuito mediante el contrato v2; la API responde 409.

La confirmación dura cinco minutos y está vinculada a la sesión, cuenta,
dispositivo, raíces y revisiones de pertenencia. Se verifica después de obtener
el bloqueo de escritura. Solo se almacena su hash. Su consumo y la unión son
atómicos. Repetir una confirmación ya completada, mientras siga vigente y la
sesión sea válida, devuelve el estado actual sin volver a sumar deudas.

Si cambia el alcance de la unión, se devuelve device_confirmation_stale (409).
El cliente debe preparar y mostrar de nuevo el aviso, no aceptarlo automáticamente.
Un cambio ordinario de saldo no invalida el alcance: se utiliza la deuda vigente
al confirmar. Repreparar invalida el token anterior de esa sesión/dispositivo.

Una respuesta de confirmación perdida puede recuperarse reintentando el mismo
valor mientras sea válido; después, prepare reconoce la pareja ya vinculada.
Nunca se aplica un recibo anterior como saldo vigente. El futuro cliente debe
considerar group_id y revisión conjuntamente y evitar respuestas fuera de orden.

## Deudas y concurrencia

Cada raíz mantiene deuda en milisegundos y una referencia temporal. La recuperación
se calcula al recibir peticiones con el reloj del servidor. No existen tareas
por usuario, contadores permanentes ni un temporizador que escriba cada segundo.

Al unir raíces distintas, se normaliza cada deuda al instante actual, respetando
su propia referencia, y se suman las deudas pendientes. Nunca se usa la referencia
futura de otro grupo para acreditar tiempo que no transcurrió. Se conserva la
referencia máxima para no duplicar recuperación tras un retroceso del reloj.

La deuda no se recorta a la capacidad. Dos deudas de cinco horas en Programación
producen diez horas: cero corazones y la primera recuperación dentro de tres horas.
Unir dos alias de la misma raíz no suma otra vez. Los saldos disponibles no se suman.

Autenticación, autorización del dispositivo, resolución de raíces, unión y saldo
usan transacciones SQLite de escritura. Un fallo revierte todos los cambios del
intento, no deja media unión ni consume la confirmación. No se ejecutan verificaciones
de contraseña costosas ni llamadas externas dentro de esas transacciones.

La primitiva debit_in_transaction está reservada al futuro evaluador. No tiene
endpoint público, no verifica respuestas y NO es idempotente por sí sola. Ese
evaluador deberá guardar su recibo por (cuenta autenticada, intento), no por raíz,
para que una fusión no permita cobrar otra vez un reintento. Las pruebas incluyen
un envoltorio mínimo de recibos para comprobar esa combinación bajo concurrencia;
ese envoltorio es solo una prueba, no un evaluador de producción.

## Migración y operaciones locales

La migración añade tablas y copia una sola vez cada saldo canónico account_hearts.
No vuelve a importar los snapshots v1 por dispositivo de los que ese saldo ya
se derivó. Preserva las cuentas, sesiones, progresos y ajustes previos. Después,
account_hearts queda como archivo protegido contra cambios mediante disparadores.
La fuente operativa de corazones pasa a ser group_hearts de la raíz vigente.

Los hashes v1 dependían de la cuenta, por lo que no se inventa una correspondencia
global ni un consentimiento histórico que no existe. Las cuentas migradas deben
aceptar la primera asociación registrada por este contrato. Falta de tablas,
relaciones, claves o alguna ruta del saldo causa error; no se repara regalando vidas.

Detén ServerTec antes de respaldar, actualizar o restaurar. No ejecutes las versiones
vieja y nueva a la vez sobre la misma base. Recibe el cambio con Pull en ServerTec/main;
no vuelvas a usar Inicializar sobre un estado existente. El esquema se incorpora
al iniciar la versión nueva. No se trasladan las rutas D/E ni datos automáticamente.

El respaldo debe conservar la base y la MISMA device-hmac.key. El comando de respaldo
existente copia ambas; para este paso se exige hacerlo con el servicio detenido.
No se afirma una copia consistente de la clave recién creada durante un respaldo
en caliente. No se promete tolerancia a restaurar un backup antiguo: también
podría restaurar sesiones, consumos y asociaciones anteriores.

Existen límites LOCALES antiabuso: ocho confirmaciones recientes por cuenta y
10.000 registros de confirmación simultáneos, con limpieza acotada al recibir
peticiones. No son límites de usuarios registrados ni cuotas comerciales.
Se mantienen los límites de autenticación y peticiones del servidor. No se ha
medido una capacidad de 10.000 usuarios concurrentes.

## Validación ejecutada en este paso

Entorno aislado Linux, Python 3.13.5; dependencias directas sin cambios.

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -X dev -m pytest \
  test_servertec.py test_accounts_api.py test_consumption_groups.py \
  -q -p no:cacheprovider -W error::ResourceWarning \
  -W error::pytest.PytestUnraisableExceptionWarning
134 passed in 12.38s

python autoprueba.py
Resultado: 9/9
```

Son 59 pruebas nuevas de grupos y 75 pruebas existentes del servidor/API de cuentas.
No se ejecutó aquí toda la batería histórica de 265 pruebas. La autoprueba 9/9
conserva el contrato QA v1 y no equivale a nueve pruebas de un evaluador nuevo.

Se comprobaron cinco cuentas en un teléfono, recuperación única, cancelación,
alias transitivos, deuda superior a capacidad, consentimiento caducado o obsoleto,
revocación de sesiones, migración sin duplicados, pérdida/cambio de clave, separación
de datos privados y cierre explícito de conexiones. Se probaron confirmaciones,
uniones y débitos concurrentes; fallo SQLite intermedio; salida abrupta REAL de
un proceso durante la unión; dos secuencias independientes de 200 pasos comparadas
con otro modelo. La prueba HTTPS real incluye scrypt, registro, asociación,
confirmación de nuevo dispositivo y logout, sin secretos en logs.

No se probó Windows/PowerShell, Honor, LDPlayer, Google real, Billing real,
revocación remota Firebase, acceso público ni carga de producción. No se tocaron
los datos reales de la PC. No se realizó una auditoría independiente externa.

## Lo que sigue pendiente

Evaluador curricular autoritativo y recibos de intentos de producción; verificación
de correos y vinculación acreditada de métodos de acceso; sincronización automática
completa del progreso; UI y transporte Android; migración de datos de la app;
verificación real de Premium y Google; acceso remoto y pruebas en la PC del usuario.
Este cambio prepara el servidor, no declara completada la integración del encargo.

Referencias técnicas consultadas:
- https://www.sqlite.org/lang_transaction.html
- https://docs.python.org/3.13/library/sqlite3.html
- https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html
- https://developer.android.com/reference/android/provider/Settings.Secure#ANDROID_ID

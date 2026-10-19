# Evaluación autorizada y recibos de intentos

Esta etapa implementa en ServerTec la evaluación de respuestas gratuitas con
reglas instaladas en el servidor. El resultado, el descuento y el recibo se
confirman juntos en SQLite. La app Android aún no utiliza este endpoint.

## Alcance curricular instalado

`rules-catalog.json` contiene **364 ejercicios**, extraídos de 33 archivos de
lecciones publicados en `SimDynamics/LearnGraphicsProgramming`, rama
`codex-chat/app`, commit `621f35c5565b1f02c39576a70f657b929f1970b4`.
Se incluyen la unidad 1 de Programación 1 (5 lecciones) y la unidad 1 de
Matemáticas 1 (6 lecciones), en español, inglés y francés.

| Ejercicios instalados | Español | Inglés | Francés | Total |
|---|---:|---:|---:|---:|
| Programación: opción múltiple | 29 | 25 | 25 | 79 |
| Programación: predicción de salida | 16 | 13 | 13 | 42 |
| Programación: ordenar fragmentos | 2 | 2 | 2 | 6 |
| Matemáticas: puzzles completos | 79 | 79 | 79 | 237 |
| **Total** | **126** | **119** | **119** | **364** |

La diferencia de siete ejercicios de Programación entre ES y EN/FR corresponde
a las fuentes publicadas en ese commit. No se inventaron ejercicios ni se
modificaron sus traducciones. El catálogo no representa todo el currículo.

`rules-catalog-coverage.json` identifica cada archivo fuente, sus hashes,
las versiones de los evaluadores Android revisados y cada bloque excluido.
En esas unidades se omiten 24 ejercicios de completar código (18 `fill_code`,
3 `inline_fill_code`, 3 `drag_fill_code`) y 12 bloques de compilador C++.
No se ejecuta código enviado por el cliente. Solicitar un ejercicio no instalado
produce un error sin descuento; el cliente gratuito no debe sustituirlo por
una evaluación local autorizada por él mismo.

Matemáticas usa selección, números/fracciones, campos, orden y correspondencias.
Un puzzle con varias respuestas se evalúa como bloque completo, como en Android:
si alguna está incompleta o no es evaluable, ninguna respuesta de ese bloque
puede ocasionar un descuento. Se respetan los límites numéricos y el redondeo
DECIMAL64 previo a comprobar finitud de Android. No se incorpora un CAS ni un
intérprete de expresiones arbitrarias.

## Versiones y procedencia

Cada ejercicio tiene un ID que incluye idioma, ruta, lección y bloque. Su versión
es un SHA-256 calculado con el contenido del bloque, las reglas y la versión
semántica del evaluador. Un cambio en otro archivo, el commit global o la posición
del bloque no cambia esa versión. Cambiar la pregunta, las opciones o el validador
sí requiere una versión distinta. Los campos de procedencia quedan registrados
por separado. La carga rechaza versiones que no correspondan a sus reglas.

El catálogo se carga al arrancar y queda inmutable. Las peticiones no pueden
instalar reglas, elegir un validador ni proporcionar una respuesta esperada.
No existe un endpoint para obtener las soluciones o subir un catálogo.
Una actualización se recibe mediante Git y requiere reiniciar el servicio.
Para admitir nuevas evaluaciones de APK anteriores deben conservarse sus versiones
de reglas; un recibo confirmado sigue siendo recuperable aunque su versión se retire.

## Contrato HTTP

`POST /v2/evaluations` requiere HTTPS, una sesión de cuenta válida en
`Authorization: Bearer <sesión>` y el dispositivo aceptado en `X-Android-Id`.
El token de pruebas v1 no sirve para suplantar una cuenta v2.

El cuerpo admite exactamente estos cuatro campos:

```json
{
  "attempt_id": "8c0c3f67-5523-420a-acf4-41e5063b9231",
  "exercise_id": "es/programming/cpp_fundamentals__programas_y_ejecucion__fuente_compilacion_y_diagnostico/editor_compilador",
  "exercise_version": "38f92d4bf8cd77619ba0820433c054f372027661f0eb941f50ee685b650add92",
  "answer": 1
}
```

El UUID del ejemplo debe sustituirse por uno nuevo para un intento nuevo. La
respuesta `1` significa el índice 1, contando desde cero. Identidad, grupo y ruta
se resuelven en el servidor. Campos como `correct`, `correcto`, `premium`, `route`,
`saldo`, `account_id` y `validator` son rechazados. También se rechazan campos JSON
duplicados, NaN, Infinity y tipos que necesitarían coerción. El cuerpo total está
limitado a 16 KiB y la respuesta canónica a 8 KiB, con límites de profundidad,
listas y objetos. Los números matemáticos se envían como texto para preservar
su representación decimal o fraccionaria.

| Tipo | Forma de `answer` |
|---|---|
| Opción múltiple | Índice entero desde cero; no booleano, texto ni decimal |
| Predicción de salida | Texto; comparación exacta o recorte de extremos según la regla |
| Ordenar código | Lista de textos de fragmentos, conservando sus repeticiones |
| Puzzle matemático | Objeto por ID de respuesta que incluye todas las respuestas del bloque |

Ejemplos de valores individuales dentro de un puzzle matemático:

```json
{
  "respuesta_opcion": {"type": "choice", "selected": ["opcion_a"]},
  "respuesta_numero": {"type": "text", "value": "3/4"},
  "respuesta_campos": {"type": "fields", "values": {"x": "2", "y": "5"}},
  "respuesta_orden": {"type": "order", "ids": ["a", "b", "c"]},
  "respuesta_pares": {"type": "matching", "pairs": {"izquierda": "derecha"}}
}
```

Estos IDs ilustrativos deben reemplazarse por los del ejercicio instalado; no
constituyen una respuesta válida para el ejemplo de opción múltiple anterior.

### Resultado confirmado: HTTP 200

La respuesta contiene `status: evaluated`, `replayed`, `receipt` y `hearts`.

`receipt` conserva `attempt_id`, `exercise_id`, `exercise_version`, `correct`,
`charged_hearts`, `duplicate_answer`, `evaluated_at_ms` y `confirmed_at_ms`.
Una respuesta incorrecta completa descuenta exactamente un corazón; una correcta
no descuenta. `charged_hearts` expresa el cargo **histórico de ese recibo**.
Si `replayed` es verdadero, no se ha cobrado otra vez aunque el recibo siga
indicando su cargo original de 1.

`hearts` es el saldo actual en la misma transacción: cuenta, ruta, grupo vigente,
disponibles, máximo, revisión, referencia efectiva del reloj y próxima recuperación.
Una repetición conserva el recibo original y calcula de nuevo el saldo actual.
Nunca devuelve un saldo histórico como si fuera vigente tras una fusión.
La app debe considerar conjuntamente grupo y revisión y evitar aplicar respuestas
fuera de orden. `next_heart_at_ms` permite mostrar la espera sin consultas continuas.

### Sin corazones: HTTP 409

La respuesta incluye `status: pending`, `error: hearts_empty`, `attempt_id` y
`hearts`, sin corrección ni recibo confirmado. El servidor no evalúa una respuesta
nueva con saldo cero, ni siquiera para averiguar si sería correcta.
Un intento válido queda ligado a su respuesta: podrá reenviarse con el mismo UUID
después de recuperar un corazón. Cambiar sus parámetros con ese UUID es conflicto.
Hay como máximo 32 intentos pendientes por cuenta; el límite no impide continuar
uno existente ni confirmar nuevas respuestas cuando hay corazones disponibles.

Los intentos mal formados, ejercicios desconocidos y fallos técnicos no crean un
recibo de evaluación ni descuentan. La app conserva localmente los borradores y
los UUID hasta resolver una respuesta de red perdida. No debe generar otro UUID
por timeout o reinicio. Sin conexión, una evaluación gratuita nueva queda pendiente.

### Reintentos y respuestas repetidas

La clave del intento es `(cuenta autenticada, UUID)`. La huella incluye el ID del
ejercicio, su versión y la respuesta JSON canónica. El orden de las claves de
objetos es irrelevante; se conservan tipos, texto y orden de listas. Un cambio
con el mismo UUID recibe `attempt_conflict` (409), pendiente o confirmado.

Además, la misma respuesta concreta con otro UUID reutiliza el resultado de esa
cuenta, ejercicio y versión: A → B → A produce dos cargos cuando A y B son
incorrectas. El tercer recibo lleva `duplicate_answer: true` y `charged_hearts: 0`.
Esta repetición también puede recuperar su resultado con saldo cero. No se
ejecuta otra evaluación. La normalización de la huella no intenta demostrar
equivalencia algebraica entre textos diferentes.

Cerrar sesión, recuperar acceso, reiniciar el servidor, cambiar de dispositivo
aceptado o unir grupos no reinicia esas claves. Otra cuenta no puede leer ni
reutilizar el resultado privado de la primera por compartir sus corazones.
Todo reintento vuelve a comprobar la sesión y la asociación del dispositivo.

### Errores principales

| HTTP | Código o caso | Consecuencia |
|---|---|---|
| 401 | Sesión ausente, revocada o inválida | Sin acceso al recibo ni al saldo |
| 409 | `device_confirmation_required` | Completar la confirmación pendiente |
| 409 | `attempt_conflict` | No reutilizar el UUID para otra respuesta |
| 409 | `hearts_empty` | Respuesta pendiente con próxima recuperación |
| 409 | `exercise_version_unavailable` | Esa versión no permite una evaluación nueva |
| 404 | `unknown_exercise` | Ejercicio fuera del catálogo instalado |
| 422 | JSON, tipo, forma o respuesta incompleta/no evaluable | Sin descuento |
| 429 | `pending_attempt_limit` o limitación HTTP existente | Reducir/reintentar peticiones según el estado |
| 503 | Estado/almacenamiento no disponible | Sin éxito aparente; reenviar el mismo intento |

## Persistencia, consumo y migración

La única transacción de escritura obtiene la hora después de adquirir el bloqueo,
verifica sesión y dispositivo, resuelve el grupo, consulta el recibo, valida la
respuesta y consulta disponibilidad. Cuando procede, evalúa con la regla pura,
descuenta y guarda resultado y recibo antes de confirmar. No ejecuta llamadas de
red, compiladores ni verificaciones costosas de contraseñas dentro del bloqueo.

`evaluation_results` guarda una vez el resultado de cada respuesta concreta y
`evaluation_attempts` sus UUID pendientes o confirmados. Se conservan huellas,
sin almacenar la respuesta original, la contraseña, el token o el ANDROID_ID.
Los recibos no se borran automáticamente: esa permanencia sostiene la idempotencia
después de reinicios y fusiones. Los índices permiten buscar por cuenta/UUID o
huella sin recorrer el historial completo.

La migración añade tablas, índices y guardas; no modifica los saldos, cuentas,
credenciales, progreso ni preferencias existentes. Su marca también se conserva
en `auth_meta`. Una tabla, índice o guarda perdida provoca un fallo al arrancar;
no se recrea como un historial vacío. Los resultados son inmutables y los recibos
confirmados no pueden editarse ni eliminarse por las operaciones ordinarias.

La recuperación conserva 8 corazones en Programación, 12 en Matemáticas/Física y
un corazón por hora por grupo/ruta. Se calcula al atender peticiones, incluidos
los reintentos, respetando deuda superior a capacidad y retrocesos del reloj.
Este endpoint cubre consumo gratuito: no concede ni propaga Premium, y no es el
flujo de evaluación offline de una compra legítima. Esa integración permanece
separada y pendiente de Android/verificación oficial de compras.

## Actualización e importación local

Para recibir esta entrega, detener ServerTec, respaldar su estado con la misma
`device-hmac.key`, hacer Pull de `SimDynamics/ServerTec/main` y arrancar de nuevo.
No ejecutar Inicializar sobre el estado existente. No hay dependencias nuevas,
puertos nuevos ni acciones sobre el repositorio Android. El catálogo viene en Git;
no es necesario ejecutar el importador para usar esta entrega del servidor.

Para preparar futuros catálogos, el operador puede ejecutar `import_exercises.py`
con `--repo`, `--commit`, `--output` y `--coverage`. El origen debe ser un checkout
Git del repositorio Android correcto y el SHA publicado explícito. Se leen los
blobs de ese SHA, no los cambios de trabajo sin publicar. Opcionalmente `--unit`
y `--locale` seleccionan unidades e idiomas; por defecto usa las dos unidades
iniciales y ES/EN/FR. `--replace` permite reemplazar sólo los archivos de salida
designados. El importador verifica hashes y rechaza un evaluador Android cambiado
hasta que se revise su compatibilidad. No modifica Android ni descarga datos.
El operador debe comprobar que el SHA elegido esté publicado: el importador
comprueba el snapshot Git local y no consulta GitHub. Para esta entrega sí se
comprobó directamente el HEAD publicado y los archivos fijados a ese SHA.

La importación automática también omite expectativas numéricas almacenadas como
JSON flotante y tolerancias distintas de cero, cuya conversión Java/Python no se
ha equiparado. Ninguna de las 364 reglas instaladas necesita esos casos. Las
reglas normalizadas del motor puro permiten tolerancia racional explícita, sin
afirmar compatibilidad automática con esos formatos fuente todavía no revisados.

Antes de distribuir un catálogo ampliado hay que revisar su informe de omisiones,
validar las respuestas con los evaluadores fuente y conservar las versiones que
necesiten los clientes instalados. Un hash demuestra integridad y procedencia
registrada; la autorización viene de revisar e instalar el archivo en el servidor.

## Verificación y siguientes etapas

`test_evaluations.py` comprueba contabilidad, privacidad, pendientes, reintentos,
concurrencia, fusiones y terminación real de procesos antes/después del commit.
`test_evaluations_api.py` comprueba los límites HTTP y un servidor HTTPS real con
catálogo instalado, scrypt, reinicio y recuperación del mismo recibo. Las pruebas
del catálogo/importador cubren los formatos reales y entradas adversas. Los
resultados exactos de la ejecución publicada figuran en `RESULTADOS.md`.

Faltan ampliar el catálogo a otros ejercicios y unidades; integrar la llamada,
los UUID durables y las pantallas en Android; verificar correos y vinculación
acreditada; sincronización automática completa; y pruebas reales de Google,
Premium, Windows y acceso externo. Esta etapa no completa esos sistemas.

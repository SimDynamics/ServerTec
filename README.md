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

## Qué funciona en esta entrega

* HTTPS con autoridad propia, certificado del servidor y validación real. Nunca `verify=False`, `curl -k` ni un verificador que acepte cualquier certificado.
* SQLite con transacciones y respuestas idempotentes: repetir el mismo UUID de descuento no vuelve a gastar una vida; cambiar la ruta con el mismo UUID se rechaza.
* Saldo de corazones persistente por **cuenta Google autenticada, dispositivo identificado por ANDROID_ID y ruta**: 8 en Programación y 12 en Matemáticas/Física. Cada ruta recupera una vida por hora con el reloj del servidor. ANDROID_ID se usa exclusivamente como identificador del dispositivo, protegido en SQLite mediante HMAC con una llave privada fuera de Git. El cliente Android aún necesita integrarse; esto no constituye protección infalible contra un APK modificado.
* Sincronización autenticada de **lecciones, unidades y cursos completados**, más grupos permitidos de ajustes portables (idioma, apariencia, tamaño de texto, navegación, atajos y narración compatible). Se excluyen páginas, intentos parciales, audios, rutas de almacenamiento y datos sensibles.
* Verificador de tokens Firebase firmados con RS256: valida emisor, audiencia, caducidad, identificador y proveedor Google. Claves públicas de Google almacenadas temporalmente en memoria, no consultadas en cada petición.
* Modo de prueba local con token aleatorio, separado de la identidad Google real. No acepta un UID enviado en una cabecera. El token de pruebas nunca está incluido en Git.
* Límite de tamaño de petición, plazo de recepción de cuerpo, concurrencia y frecuencia. Sin interfaz administrativa pública ni archivos estáticos.
* Copia SQLite consistente: `-Accion Respaldo`, incluyendo una copia privada de `device-hmac.key` cuando ya exista. La restauración necesita conservar la misma llave para reconocer los identificadores de dispositivo. El respaldo sigue en el mismo disco y **no protege de una avería**; falta preparar una copia externa cifrada y probar su recuperación.

Los límites de frecuencia y tamaño son protecciones configuradas por nosotros, no cuotas comerciales. No representan una prueba de capacidad para 10 000 usuarios. No se han realizado ensayos de carga de esa escala.

## Contrato API preliminar

Las rutas `/v1/*` necesitan `Authorization: Bearer <token>`. En pruebas, leer el token solo desde el archivo local protegido; nunca copiarlo al chat ni incrustarlo en una APK. La app final usará el token individual de Google/Firebase. **Para corazones en producción también se exige `X-Android-Id`**, el `ANDROID_ID` hexadecimal de 16 caracteres, enviado mediante HTTPS. Este identificador no sustituye la autenticación ni es una prueba criptográfica de integridad del dispositivo; los clientes QA de loopback todavía admiten ausencia de cabecera para compatibilidad con pruebas anteriores.

| Método | Ruta | Función |
|---|---|---|
| GET | `/health` | Estado mínimo, sin datos personales |
| GET | `/v1/hearts/programming` | Saldo y referencia de recarga |
| GET | `/v1/hearts/math_physics` | Saldo de la otra ruta |
| POST | `/v1/hearts/debits` | `operation_id` UUID estable y `route` |
| GET | `/v1/progress` | Lecciones, unidades y cursos completados de la identidad autenticada |
| PUT | `/v1/progress/completions` | `kind: lesson/unit/course`, `course`, `item` |
| GET | `/v1/settings` | Preferencias portables por namespace con revisión |
| PUT | `/v1/settings/{namespace}` | Documento de preferencias validado, `expected_revision` y `values` |

Un reintento devuelve el recibo original, posiblemente antiguo: no debe sustituir ciegamente un saldo posterior. El cliente debe usar la revisión/tiempo y consultar saldo cuando corresponda. Una operación rechazada por saldo cero sigue rechazada si se reintenta con ese UUID después de una recarga; el intento nuevo necesita otro UUID. No hay endpoint para fijar saldo o `premium=true` desde el cliente.

**Este contrato todavía no valida en el servidor las soluciones de los puzzles.** Un cliente alterado podría omitir el aviso de fallo. Idempotencia evita doble cobro y el saldo guardado evita un nuevo regalo al reinstalar una identidad ya registrada; no prueba que todo uso se haya registrado. No sustituir aún `AttemptRepository` por este prototipo.

Los completados son declaraciones autenticadas del estudiante, no títulos certificados por un evaluador remoto. La validación de IDs contra el catálogo se añadirá antes de exposición pública.

## IPv6 dinámica: bloqueo de publicación aún abierto

La prueba del usuario mostró dos prefijos diferentes después de reiniciar el router. No se fija la dirección desactivando DHCP de Windows. **Este proyecto no promete descubrimiento automático de una IP nueva sin un punto de referencia estable.** Guardar la IP nueva en el mismo servidor que ya no se encuentra no resuelve el problema.

Para pruebas iniciales: loopback y, en la siguiente fase, ADB con un cliente de pruebas que confíe exclusivamente en nuestra autoridad. Para red local/remota: dirección actual comunicada explícitamente y certificado con su IP en SAN. Cambiar de IP requiere actualizar la dirección en el cliente y emitir un certificado válido para la nueva IP, conservando la autoridad. No se desactiva la verificación de nombre.

No se introducen DNS dinámicos, dominio, túnel, proxy ni un repositorio público de descubrimiento. La reconexión automática pública queda pendiente de una decisión que satisfaga las restricciones. También falta comprobar IPv4 WAN/CGNAT, firewall del router y acceso desde una red externa; una IPv6 global local no demuestra accesibilidad ni compatibilidad con clientes solo IPv4.

## Git y secretos

Estado: `D:\Projects\ServerTec\state`. Contiene base de datos, token de pruebas, configuración, certificado y claves. El servidor rechaza ubicarlo dentro del código. La CA privada queda cifrada; la clave de ejecución se protege mediante permisos locales y no se sirve por HTTP. El script no instala la CA como autoridad del sistema.

`.gitignore` es una protección adicional, no cifrado, y no borra secretos ya subidos. No mover bases o claves al repositorio al publicar. El certificado público de la autoridad podrá incorporarse al cliente en la fase Android; la clave privada nunca.

## Próxima arquitectura y tareas pendientes

**Alcance revisado:** sincronizar lecciones, unidades y cursos completados; los ajustes permanecen locales. Los endpoints de ajustes ya escritos se conservan como código heredado, no como autorización para sincronizarlos desde Android. El backend ya contiene estos contratos, así como separación de corazones por cuenta y dispositivo; **la aplicación Android todavía no está integrada**. La cuenta de desarrollador de Google Play Console todavía no puede crearse por su coste de registro; esto no bloquea el resto del trabajo. La recuperación offline aprobada aún necesita su motor de reloj y su conciliación cliente-servidor; este paso no cambia esas reglas ni añade temporizadores por usuario.

Pendiente: ejecutar estos scripts en Windows y la prueba de HTTPS en tu PC; diagnosticar acceso público y cambios de dirección; configurar Google/Firebase real y revocación de sesiones; integrar la app en una variante QA sin destruir datos; implementar los contratos acordados de corazones/offline; revisar identidad y borrado de cuenta; comprobar Google Play Billing real; actualización/renovación de certificados; respaldo externo y restauración; aislamiento del servicio, inicio automático y recuperación tras corte; pruebas de carga; auditoría de dependencias y revisión de seguridad.

Premium sigue separado. Esta entrega no concede Premium ni simula compras reales. No elimina offline ni altera la app. No tiene dependencias de Firestore.

## Referencias técnicas

* https://fastapi.tiangolo.com/deployment/manually/
* https://uvicorn.dev/settings/
* https://docs.python.org/3.13/library/sqlite3.html
* https://firebase.google.com/docs/auth/admin/verify-id-tokens
* https://developer.android.com/privacy-and-security/security-config
* https://git-scm.com/docs/gitignore
* https://learn.microsoft.com/en-us/powershell/module/nettcpip/get-netipaddress

Las pruebas de esta entrega se ejecutaron en Linux con Python 3.13; eso no equivale a una prueba en Windows, Honor o LDPlayer. `RESULTADOS.md` identifica exactamente lo comprobado.

# ServerTec / servidor independiente de LearnGraphicsProgramming

Servidor propio para LearnGraphicsProgramming. Código aislado de Android. **No está conectado todavía a la app ni habilitado para Internet o Google Play.** No modifica APK, voces, Enter, progreso local, router, DNS ni firewall.

## Ubicación y alcance

**Repositorio actual:** \`SimDynamics/ServerTec\` (privado, rama \`main\`), independiente de \`SimDynamics/LearnGraphicsProgramming\`. **Copia local:** \`E:\PersonalFiles\Projects\ServerTec\`. La migración por Git y la retirada de \`server/ServerTec\` del árbol \`main\` de la app ya se completaron. El repositorio público de recursos no participa. Claves privadas, certificados y SQLite permanecen fuera del código.

Esta implementación usa Python 3.13+, FastAPI, Uvicorn, SQLite, cryptography y PyJWT. Son herramientas ejecutadas en tu equipo, sin suscripción de hosting ni cuota de operaciones de un proveedor. **No es el ejemplo previo en ASP.NET/C#: es una implementación Python independiente que se ha podido ejecutar y probar en este entorno.** No es un servicio de FastAPI alojado. La descarga de dependencias usa el registro de paquetes; el servidor no depende de ese registro después de instalarlas.

No se instala nada automáticamente con el diagnóstico. No hay Docker Desktop, túneles, dominios, plataformas de despliegue ni GitHub Actions nuevos. GitHub solo conserva código fuente.

## Primera ejecución en Windows

Tras clonar el repositorio privado en \`E:\PersonalFiles\Projects\ServerTec\`, **las actualizaciones posteriores llegan por Git, no por ZIP**. Verificar primero los cambios locales; si no hay conflictos ni modificaciones propias, usar \`git pull --ff-only origin main\`. Abrir PowerShell normal, sin administrador:

```powershell
Set-Location -LiteralPath 'E:\PersonalFiles\Projects\ServerTec'
powershell -NoProfile -ExecutionPolicy Bypass -File .\ServerTec.ps1 -Accion Diagnostico
```

`Bypass` solo afecta a ese proceso, no cambia permanentemente la política de Windows. El diagnóstico lee las direcciones, prefijos reales, rutas y disponibilidad de Python/ADB. No escanea Internet. El informe completo queda fuera de Git, en `%LOCALAPPDATA%\ServerTec\reports`. Compartir solo su resumen.

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
* Saldo inicial persistente por identidad y ruta: **8 en Programación y 12 en Matemáticas/Física por decisión expresa del usuario**, recuperación continua de una vida/hora, calculada en el servidor al consultar. La separación por identidad **y dispositivo** está planificada, pero todavía no implementada; ver el documento de arquitectura.
* Registro de unidades y cursos completos únicamente. No hay endpoint para páginas, intentos, ajustes o lecciones individuales.
* Verificador de tokens Firebase firmados con RS256: valida emisor, audiencia, caducidad, identificador y proveedor Google. Claves públicas de Google almacenadas temporalmente en memoria, no consultadas en cada petición.
* Modo de prueba local con token aleatorio, separado de la identidad Google real. No acepta un UID enviado en una cabecera. El token de pruebas nunca está incluido en Git.
* Límite de tamaño de petición, plazo de recepción de cuerpo, concurrencia y frecuencia. Sin interfaz administrativa pública ni archivos estáticos.
* Copia SQLite consistente e integridad comprobada: `-Accion Respaldo`. Una copia en el mismo disco NO protege de una avería; falta preparar la copia externa.

Los límites de frecuencia y tamaño son protecciones configuradas por nosotros, no cuotas comerciales. No representan una prueba de capacidad para 10 000 usuarios. No se han realizado ensayos de carga de esa escala.

## Contrato API preliminar

Las rutas `/v1/*` necesitan `Authorization: Bearer <token>`. En pruebas, leer el token solo desde el archivo local protegido; nunca copiarlo al chat ni incrustarlo en una APK. La app final usará el token individual de Google/Firebase.

| Método | Ruta | Función |
|---|---|---|
| GET | `/health` | Estado mínimo, sin datos personales |
| GET | `/v1/hearts/programming` | Saldo y referencia de recarga |
| GET | `/v1/hearts/math_physics` | Saldo de la otra ruta |
| POST | `/v1/hearts/debits` | `operation_id` UUID estable y `route` |
| GET | `/v1/progress` | Unidades/cursos completados de la identidad autenticada |
| PUT | `/v1/progress/completions` | `kind: unit/course`, `course`, `item` |

Un reintento devuelve el recibo original, posiblemente antiguo: no debe sustituir ciegamente un saldo posterior. El cliente debe usar la revisión/tiempo y consultar saldo cuando corresponda. Una operación rechazada por saldo cero sigue rechazada si se reintenta con ese UUID después de una recarga; el intento nuevo necesita otro UUID. No hay endpoint para fijar saldo o `premium=true` desde el cliente.

**Este contrato todavía no valida en el servidor las soluciones de los puzzles.** Un cliente alterado podría omitir el aviso de fallo. Idempotencia evita doble cobro y el saldo guardado evita un nuevo regalo al reinstalar una identidad ya registrada; no prueba que todo uso se haya registrado. No sustituir aún `AttemptRepository` por este prototipo.

Los completados son declaraciones autenticadas del estudiante, no títulos certificados por un evaluador remoto. La validación de IDs contra el catálogo se añadirá antes de exposición pública.

## IPv6 dinámica: bloqueo de publicación aún abierto

La prueba del usuario mostró dos prefijos diferentes después de reiniciar el router. No se fija la dirección desactivando DHCP de Windows. **Este proyecto no promete descubrimiento automático de una IP nueva sin un punto de referencia estable.** Guardar la IP nueva en el mismo servidor que ya no se encuentra no resuelve el problema.

Para pruebas iniciales: loopback y, en la siguiente fase, ADB con un cliente de pruebas que confíe exclusivamente en nuestra autoridad. Para red local/remota: dirección actual comunicada explícitamente y certificado con su IP en SAN. Cambiar de IP requiere actualizar la dirección en el cliente y emitir un certificado válido para la nueva IP, conservando la autoridad. No se desactiva la verificación de nombre.

No se introducen DNS dinámicos, dominio, túnel, proxy ni un repositorio público de descubrimiento. La reconexión automática pública queda pendiente de una decisión que satisfaga las restricciones. También falta comprobar IPv4 WAN/CGNAT, firewall del router y acceso desde una red externa; una IPv6 global local no demuestra accesibilidad ni compatibilidad con clientes solo IPv4.

## Git y secretos

Estado: `%LOCALAPPDATA%\ServerTec\state`. Contiene base de datos, token de pruebas, configuración, certificado y claves. El servidor rechaza ubicarlo dentro del código. La CA privada queda cifrada; la clave de ejecución se protege mediante permisos locales y no se sirve por HTTP. El script no instala la CA como autoridad del sistema.

`.gitignore` es una protección adicional, no cifrado, y no borra secretos ya subidos. No mover bases o claves al repositorio al publicar. El certificado público de la autoridad podrá incorporarse al cliente en la fase Android; la clave privada nunca.

## Próxima arquitectura y tareas pendientes

**Diseño objetivo y dudas de alcance por resolver:** [`docs/ARQUITECTURA-OBJETIVO.md`](docs/ARQUITECTURA-OBJETIVO.md). El código ejecutable actual no implementa todavía corazones separados por dispositivo, la nueva sincronización de lecciones/ajustes ni el cliente Android. La cuenta de desarrollador de Google Play Console todavía no puede crearse por su coste de registro; esto no bloquea el resto del trabajo.

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

# ServerTec: arquitectura objetivo de identidad, corazones y sincronización

**Fecha de decisión:** 2026-10-17. **Estado:** diseño en evolución, **no** implementación final.
Documento de trabajo para la siguiente etapa. Distingue comportamientos elegidos, limitaciones técnicas y decisiones aún abiertas. Los contratos `/v1/` documentados en README siguen reflejando lo que ejecuta el código actual.

## 1. Hechos ya acordados

- **Capacidad deliberada por ruta:** Programación = **8** vidas; Matemáticas/Física = **12**. Recuperación individual de **1 vida cada hora**, hasta el máximo de cada ruta. No «normalizar» ni igualar los dos máximos.
- **Servidor propio:** Python, SQLite y HTTPS; Git exclusivo: `SimDynamics/ServerTec` (privado, rama `main`). No almacenar datos reales dentro del código ni en GitHub.
- **Autenticación:** la identidad de cuenta se obtiene de un token Firebase Authentication verificado en ServerTec después de «Continuar con Google». No aceptar `uid` arbitrario del cliente.
- **Progreso educativo:** conservar íntegramente en el dispositivo los estados de estudio necesarios para trabajar offline, incluidos páginas, intentos, puzzles parciales y estados internos. **Se sincronizan, como mínimo, unidades y cursos completados**. Ver §5 sobre lecciones y ajustes.
- **Premium:** compra única no consumible mediante Google Play Billing; restauración al abrir la app consultando las compras disponibles, más conservación del último estado legítimamente verificado para uso offline. No conceder Premium por un booleano libre enviado por el cliente. No se necesita Firestore para este diseño.
- **Restricción presupuestaria:** la cuenta de Google Play Console aún no está creada porque su registro requiere un pago que el usuario todavía no puede hacer. Continuar la implementación y las pruebas independientes de Play. No simular que hubo compras verificadas ni exigir ese pago para las etapas anteriores.

## 2. Corazones separados por cuenta y dispositivo

**Requisito de producto:** cambiar de cuenta Google o cambiar de dispositivo puede producir otro saldo inicial. Borrar exclusivamente los datos de la aplicación, desinstalar/reinstalarla con la misma firma o cambiar manualmente la hora **no debe** regalar de nuevo las vidas mientras sea posible identificar la misma cuenta y dispositivo contra la autoridad persistente.

**Diseño para implementar (aún no activo en la API):**

- Cada estado de corazones se identifica de manera lógica mediante `(firebase_uid_autenticado, dispositivo, ruta)`; cada ruta conserva su propio saldo, recuperación y recibos idempotentes.
- Android 8+: leer `Settings.Secure.ANDROID_ID` con la misma identidad de usuario y clave de firma. No utilizarlo como autenticación ni como secreto. Es un identificador **declarado por el cliente**, susceptible de falsificación en clientes modificados.
- El servidor recibe el identificador **solo por HTTPS**, lo valida y lo pseudonimiza mediante HMAC-SHA256 con un secreto de instalación guardado fuera del repositorio (no registrar el identificador en logs ni usarlo en URL). Relacionarlo siempre con el UID obtenido de Firebase; jamás aceptar solo ANDROID_ID para consultar saldos.
- Usar el **reloj del servidor** para acreditar recuperación. Revisar que el reloj del servidor no retroceda arbitrariamente y que una migración SQLite nunca reinicie saldos existentes. Establecer esquema de migración y respaldo previo antes de sustituir `hearts(uid, route)`.
- Mantener los identificadores UUID de cada operación de descuento y los recibos idempotentes; un reintento no debe descontar dos veces ni aplicar una respuesta obsoleta sobre un saldo nuevo.
- Una cuenta nueva en el mismo teléfono obtiene un contexto distinto; otra instalación firmada con una clave diferente puede obtener otro ANDROID_ID y no se considera el mismo dispositivo.

**Límite honesto:** ninguna API basada únicamente en el ANDROID_ID informado por el APK impide su falsificación por un cliente alterado. Este diseño evita reinicios triviales por borrado de datos con acceso al servidor, pero **no garantiza** que un atacante técnicamente avanzado no pueda cambiar la identidad de dispositivo. Una validación más robusta podría requerir mecanismos de integridad adicionales, sujetos a infraestructura y autorizaciones.

**Sin conexión tras borrar datos:** si se eliminaron las preferencias y la copia local del saldo, la aplicación **no puede recuperar** el saldo real sin consultar ServerTec. Debe mostrar un estado pendiente de sincronización, nunca inventar ocho o doce vidas como si fueran nuevas. Si el servidor doméstico no está accesible, la disponibilidad inmediata de esta recuperación tampoco puede prometerse.

## 3. Reloj local, suspensión, cierre y reinicio

- `SystemClock.elapsedRealtime()` es monotónico durante **el mismo arranque**, incluye suspensión profunda y continúa aunque se cierre la aplicación. No es un reloj de proceso.
- Al apagar o reiniciar Android su origen se restablece. Un valor de `elapsedRealtime()` guardado antes del reinicio **no se puede restar directamente** del valor del nuevo arranque.
- Android usa el reloj monotónico para **mostrar** un contador local desde la última sincronización; ServerTec usa su propio reloj para determinar el saldo confirmado.
- Si hay reinicio, pérdida de datos locales o incertidumbre en los tiempos, reconciliar con el servidor. Mientras tanto usar el último estado verificado si aún está disponible y definir una política explícita de juego offline, sin crear corazones nuevos por una hora del sistema manipulada.
- El servidor continúa acumulando recuperación mientras el teléfono está apagado, hasta la capacidad de cada ruta; el teléfono la reflejará cuando vuelva a comunicarse. Antes de sincronizar no puede demostrar cuánto pasó si carece de una fuente de tiempo fiable.
- Los descuentos de respuestas incorrectas en offline requieren una **cola durable** y una regla de reconciliación; debe decidirse la política de deuda, conflictos, agotamiento e intentos rechazados. No afirmar que un cliente offline no modificable está garantizado.

Referencias oficiales:
- https://developer.android.com/reference/android/os/SystemClock
- https://developer.android.com/reference/android/provider/Settings.Secure

## 4. Separación de responsabilidades

| Datos | Dónde deben vivir |
| --- | --- |
| Cuenta e identidad Google | Firebase Authentication; ServerTec verifica tokens y conserva solo datos necesarios para el servicio |
| Corazones y tiempo de recuperación autoritativo | ServerTec (SQLite), separados por cuenta, dispositivo y ruta; caché local para UX/offline |
| Páginas, puzzles parciales, intentos, lector, audio generado y estados de sesión de estudio | Persistencia local Android; no borrarlos como parte de esta migración |
| Unidades y cursos completados | Cuenta autenticada en ServerTec; fusionar sin borrar completados válidos |
| Lecciones completadas | **Pendiente de confirmación del alcance cloud, §5** |
| Ajustes que se pueden sincronizar | **Pendiente de confirmación del alcance cloud, §5** |
| Recursos descargados, rutas de archivos, claves, estados sensibles del dispositivo | Locales; no subir materiales binarios ni secretos como «ajustes» |
| Premium y compras | Google Play Billing cuando exista Play Console; caché local del derecho previamente verificado; verificar reclamaciones según contrato de seguridad, sin confiar en booleanos del APK |

## 5. Decisión pendiente que bloquea únicamente la nueva sincronización

El usuario indicó primero que, por contar con servidor propio, desea **sincronizar también ajustes y lecciones completadas**. En el mismo mensaje aparecieron reglas anteriores de «ajustes solo locales» y la conclusión «nube solo unidades y cursos». Estas reglas **no son equivalentes**. Antes de cambiar tablas o endpoints de progreso, confirmar solo una de estas opciones:

- **A (propuesta nueva):** cuenta sincroniza unidades, cursos, lecciones completadas y un conjunto seleccionado de ajustes portables. Páginas, puzzles parciales, intentos, recursos descargados y rutas permanecen locales.
- **B (alcance reducido):** cuenta sincroniza únicamente unidades y cursos; lecciones y ajustes permanecen locales, y estos se pierden al borrar datos/reinstalar, salvo las copias explícitas del usuario.

Si se elige A, separar *ajustes portables* (tema, idioma o preferencias de lectura con significado entre dispositivos) de *ajustes dependientes de dispositivo* (voces instaladas, archivos, hardware, cachés, credenciales, posición de audio), definir catálogo y migración, y resolver actualizaciones concurrentes. No crear una tabla genérica que replique indiscriminadamente todo el estado de Android.

## 6. Estado de desarrollo y próximas comprobaciones

**Implementado a 2026-10-17:** `/v1/hearts/{route}` y descuentos por `(uid, route)`, progreso solo `unit/course`, Firebase verifier preliminar, SQLite, HTTPS local y pruebas automatizadas ejecutadas previamente en Linux. **No está implementado** todavía el aislamiento por dispositivo ni el cliente Android; no atribuirles pruebas inexistentes.

**Siguiente orden técnico:**

1. Actualizar documentación y comprobar ejecución de `Preparar` y `AutoPrueba` en Windows real, sin tocar Android.
2. Diseñar versión nueva del contrato de corazones, migración transaccional de SQLite, HMAC y pruebas para cuentas/dispositivos, borrado de datos, reloj alterado, reintentos, reinicio y desconexión. Conservar y verificar los estados previos.
3. Tras resolver §5, implementar progreso y ajustes acordados, con validación de IDs, fusiones y pruebas por usuario.
4. Integrar QA en Android, primero vía HTTPS local/ADB, sin sustituir componentes productivos hasta comprobarlos en Honor y LDPlayer.
5. Completar identidad real, conectividad Telmex, recuperación, respaldos externos, privacidad y consentimiento. Google Play Billing completo permanece dependiente de la creación futura de la cuenta de desarrollador.

No ejecutar `reset --hard`, force push, borrados de datos ni apertura automática de puertos para acelerar estos pasos.

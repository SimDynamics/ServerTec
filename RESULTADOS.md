# Validación de la primera entrega

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

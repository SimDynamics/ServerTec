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

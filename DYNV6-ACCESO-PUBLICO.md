# Acceso publico dynv6: zona creada, conexion aun pendiente

## Estado verificado mediante capturas del propietario (2026-10-19)

- La cuenta dynv6 ya contiene la zona `servertec-demo.example.invalid`.
- URL objetivo: https://servertec-demo.example.invalid/
- El formulario inicial tenia vacias las casillas IPv4 e IPv6. La captura de zona
  creada NO demuestra la existencia de registros A o AAAA funcionales.
- No existe prueba de acceso desde red externa ni de un Chrome sin CA instalada.
- Se conserva el servidor en PC, sin cambiar SQLite, claves, certificados o
  reglas de negocio y sin activar facturacion ni servicios de pago.
- YDNS sigue descartado: su dominio gratuito `ydns.eu` cerro nuevas altas.

## Seguridad prioritaria del token de DNS

La captura de instrucciones ddclient mostro un token HTTP asociado a la zona.
Tratar ese token como EXPUESTO. Desde la cuenta del propietario ir a
https://dynv6.com/keys y revocarlo/rotarlo. Generar uno nuevo exclusivo para
la automatizacion de la zona cuando corresponda. No pegar el token nuevo ni
capturar la pantalla con secretos visibles. No guardar claves API en Git,
logs ni parametros de la linea de comandos.

La API oficial `https://dynv6.com/docs/apis` permite actualizar IPv4,
IPv6 y prefijos desde un cliente local. Todavia NO se implementa ni activa
esa actualizacion: primero confirmar direcciones, acceso real y seguridad
de las credenciales.

## Paso inmediato (solo observacion, sin cambiar nada)

En la PC con ServerTec, despues de hacer Pull de este commit:

```powershell
Set-Location -LiteralPath 'E:\PersonalFiles\Projects\ServerTec'
py -3 .\demo_public_probe.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\Diagnostico-Demo-Externa.ps1
```

El primer comando comprueba DNS A/AAAA, TCP 443 y HTTPS con confianza
del sistema en Python. Un fallo de certificado es esperable con nuestra CA
privada. No desactiva certificados ni configura el navegador. El segundo
es el diagnostico Windows existente, tambien de solo lectura.

Si DNS aun no presenta registros, abrir la zona dynv6 y consultar Status
y Records. No pulsar "Set current address" a ciegas; el navegador
puede mostrar la IP de salida de una conexion que no es accesible como
servidor. Comprobar primero WAN IPv4/CGNAT y direccion IPv6 global
NO temporal que corresponda a la PC. La casilla "IPv6 prefix" de dynv6
no equivale necesariamente a publicar una AAAA del host raiz.

Comprobar la IP publica en el router y la accesibilidad real antes de
agregar A/AAAA. IPv6 debe probarse si existe, sin descartarla solo porque
IPv4 este detras de CGNAT. Ninguna direccion se publica automaticamente
con esta entrega.

## Diferencias que deben conservarse

1. DNS asignado no significa que exista un listener en Internet.
2. Listener desde la PC no prueba conectividad desde otra red.
3. TLS cifrado por nuestra CA no equivale a CA reconocida por Chrome.
4. El observador Python usa la confianza del sistema y NUNCA confirma
   por si mismo aceptacion de Chrome.
5. No abrir cuentas, evaluaciones, Premium o SQLite publicamente para
   probar el menu; usar el listener aislado de demo existente.
6. No introducir planes freemium, pagos presentes ni dependencias futuras
   de pago. El DNS de dynv6 depende de una entidad externa; su existencia
   perpetua y ausencia de futuros cambios contractuales no esta garantizada.

No modificar firewall, router, servicios, certificados ni base real sin
revision previa y permiso del propietario. No ejecutar Inicializar.

Pruebas nuevas en esta entrega: archivo `test_demo_public_probe.py`
incluido para ejecutar localmente. **No se ejecutaron en Windows durante
esta publicacion remota.** No declarar validado el acceso publico.

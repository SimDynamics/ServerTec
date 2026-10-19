# YDNS: continuidad del acceso publico de ServerTec

## Estado de esta etapa

- URL candidata: https://servertec-demo-3.example.invalid/ (aun no asignada ni verificada).
- El propietario autorizo registrar una cuenta y solicitar ese nombre.
- El registro no se ha enviado desde esta sesion; tampoco se ha aceptado ningun acuerdo o creado credenciales.
- Sin cambios al servidor, PKI, SQLite, firewall, router o API de cuentas.
- No se ha comprobado disponibilidad del nombre, conectividad entrante ni confianza publica de HTTPS.

## Alta pendiente del propietario

1. Abrir https://ydns.io/user/register y usar el correo previamente elegido.
2. Leer condiciones y privacidad y decidir si se aceptan. Completar confirmacion de cuenta en el sitio YDNS, sin proporcionar contrasenas en chats ni Git.
3. Una vez dentro, intentar crear el host `servertec-demo-3.example.invalid`. Verificar en la interfaz el sufijo que se ofrece y su disponibilidad.
4. Comprobar que el registro pertenece a la cuenta antes de emitir consultas o actualizar DNS.
5. No declarar acceso publico hasta comprobar resolucion publica, llegada desde otra red y comportamiento HTTPS real en Chrome.

## Fuentes y restricciones

- Condiciones: https://ydns.io/terms
- Alta: https://ydns.io/user/register
- API: https://ydns.io/api/v1/
- YDNS declara mantener gratuito su servicio DNS durante toda la vida del servicio y permite uso razonable. Esto no garantiza disponibilidad perpetua ni elimina su funcion de proveedor externo de nombres.
- No se requieren aqui cuotas de hosting, publicidad, tuneles comerciales ni suscripciones; ServerTec sigue en la PC.
- No se implementa facturacion, cambios de plan ni pagos futuros.

## Publicacion segura despues de obtener el nombre

Tres requisitos distintos deben comprobarse:

1. **DNS:** que registros A y/o AAAA publicados resuelvan al destino real. Para IP dinamica, la API YDNS permite cambiar el registro mediante HTTPS; no almacenar credenciales en el repositorio. No publicar direcciones internas.
2. **Acceso externo:** identificar WAN IPv4/CGNAT y alcance de IPv6; aplicar solo reglas puntuales y autorizadas para la demo aislada. Probar desde una red externa, no desde la misma LAN.
3. **HTTPS:** conservar TLS/CA privada ya implementada, sabiendo que un Chrome sin preparar no reconocera automaticamente esa CA. No desactivar validacion TLS para ocultar el bloqueo. La confianza publica se evaluara por separado sin introducir costes presentes ni futuros.

Referencia de la API de actualizacion: `https://ydns.io/api/v1/update/`. El parametro `host` es obligatorio, `ip` opcional, `record_id` opcional; requiere autenticacion. El HTTP 200 con contenido `good` confirma la actualizacion. No activar llamadas automaticas antes de tener host e IP verificadas.

## Protecciones permanentes

Nunca ejecutar Inicializar sobre el estado existente. No mover ni publicar datos de D:\Projects\ServerTec\state. No eliminar certificados existentes, claves ni pruebas. No abrir el backend completo a Internet para mostrar el menu. La demo externa debe seguir aislada del sistema real de cuentas, licencias, evaluaciones y corazones.

## Proximo hito

Una vez que el propietario confirme el nombre realmente asignado, preparar la actualizacion DNS con manejo seguro de secretos, comprobar la IPv4/IPv6 publica desde otra red y solicitar permiso antes de cambios en firewall/router. La URL candidata no debe anunciarse aun como operativa.

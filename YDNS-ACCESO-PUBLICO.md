# DNS publico: YDNS no admite altas nuevas y evaluacion de reemplazo

## Correccion verificada el 2026-10-19

El propietario accedio al panel Hosts de YDNS y encontro este aviso:

> As of July 20, 2026 we no longer provide new hosts for the ydns.eu domain. If you wish to use dynamic DNS for new hosts, you'll need to add your own domain to YDNS and add hosts on top of it.

**DESCARTADO:** no solicitar `servertec-demo-3.example.invalid` ni agregar un dominio comprado. La documentacion previa que invitaba a registrarlo quedo invalidada por la restriccion de julio de 2026. Un servicio DNS gratuito que exige un dominio propio NO resuelve el objetivo de tener un nombre publico sin costo.

YDNS no ha entregado un nuevo host al propietario. No publicar una IP, abrir puertos ni cambiar el certificado como intento de solucionar la ausencia del nombre.

## Investigacion adicional: sin servicios freemium

Se consultaron fuentes oficiales, sin abrir cuentas nuevas ni modificar ServerTec:

| Servicio | Registro de nuevos nombres | Condiciones observadas | Decision |
|---|---|---|---|
| YDNS (`ydns.eu`) | Nuevas altas cerradas 2026-07-20; exige dominio propio | DNS gratuito sobre dominios ya propios | Descartado para el nombre |
| nsupdate.info | Noticias oficiales 2023-04-13 indican suspendido el registro de cuentas nuevas | Anuncia servicio sin anuncios ni suscripcion, pero no se pueden dar por disponibles nuevas altas | Descartado en ausencia de reapertura verificada |
| dynv6 | Formulario de registro abierto el 2026-10-19; incluye correo y contrasena | Sitio oficial ofrece nombres publicos IPv4/IPv6, dice "Free for everyone"; sin plan de pago ofrecido en el formulario consultado | Candidato por evaluar, NO aprobado como solucion definitiva |
| DuckDNS | Servicio DDNS gratuito por donaciones y sin tarifa obligatoria visible | Condiciones reservan la suspension y cambios, sin compromiso irrevocable de gratuidad; su FAQ dice "free or as cheap as possible" | No acredita la continuidad incondicional exigida |

Fuentes oficiales:
- https://ydns.io/hosts/ (aviso visto por el propietario en sesion autenticada).
- https://www.nsupdate.info/custom/news.html
- https://dynv6.com/
- https://dynv6.com/users/sign_up
- https://dynv6.com/docs/apis
- https://www.duckdns.org/
- https://www.duckdns.org/tac.jsp
- https://www.duckdns.org/faqs.jsp

El sitio de dynv6 advierte expresamente que no garantiza proteccion DDoS empresarial ni SLA y recomienda no utilizarlo para servicios criticos. Que no anuncie un plan de pago no acredita disponibilidad vitalicia ni garantia contractual de gratuidad permanente. El uso comercial de una tienda, asignacion concreta y continuidad **no han sido validados**.

Propuesta de nombre para investigar, NO registrada ni confirmada:
`https://servertec-demo-2.example.invalid/`
El sufijo `dynv6.net` aparece en la documentacion de API. La disponibilidad del identificador solo debe confirmarse dentro de la cuenta autorizada.

No crear una cuenta de dynv6 sin autorizacion especifica del propietario. La autorizacion anterior cubria exclusivamente YDNS; no equivale a aceptar condiciones de otro proveedor. No introducir tarjetas, publicidad, freemium, cuotas comerciales ni contratos de pago futuro.

## Objetivo que NO se abandona

Cualquier visitante de Chrome para Windows o Android debe poder abrir la URL publica desde Internet sin configurar hosts, DNS, router o certificados en su dispositivo.

ServerTec, menu y datos siguen en la PC. Requisitos tecnicos independientes:

1. Nombre del DNS publico asignado, con mecanismo seguro para actualizar IPv4/IPv6 cuando cambien, sin planes de pago. No inventar asignaciones.
2. Acceso externo real desde redes IPv4 e IPv6. Verificar WAN/CGNAT, router/firewall y comportamiento desde fuera. Un registro AAAA no garantiza que todos los clientes tengan IPv6.
3. HTTPS actual se conserva; CA privada actual NO equivale a reconocimiento automatico de Chrome. No abrir cuentas ni rutas sensibles sin transporte seguro reconocido por el cliente. No alterar las claves ni permitir saltarse advertencias.

La continuidad comercial absoluta sin pagos futuros por proveedores externos no esta garantizada por estas fuentes. Si el proveedor desaparece, el nombre deja de resolver; la arquitectura no debe presuponer pagar despues ni describir el bloqueo como resuelto.

## Estado y siguientes pasos

- YDNS: cerrado para nuevos nombres; **no insistir ni comprar un dominio**.
- dynv6: candidato bajo investigacion; registro visible pero no efectuado, nombre no asignado, condiciones de continuidad y uso comercial pendientes de validar.
- Servidor: sin cambios de red, datos, certificados o ejecutables en esta etapa.
- Publicacion Chrome: NO probada desde Internet.

Solicitar primero autorizacion para examinar o registrar una cuenta del nuevo servicio. Hasta entonces continuar solamente comprobaciones locales y documentacion que no debiliten el servidor.

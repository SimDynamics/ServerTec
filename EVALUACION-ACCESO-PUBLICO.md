# Evaluación de acceso público sin preparar visitantes

Estado al 2026-10-19. **No se ha acreditado una combinación que cumpla todas las
condiciones económicas y de continuidad. No se integra una dependencia externa.**
Esto describe el resultado de la investigación, no una demostración de que toda
alternativa imaginable sea imposible.

## Objetivo vigente y decisión

La nueva instrucción permite evaluar otro nombre público y una CA reconocida por
Chrome. Sustituye la decisión anterior de conservar `.dynamics` y configurar los
visitantes. El servidor, menú y datos deben seguir en esta PC; los visitantes
Windows/Android deben usar Chrome normalmente, sin hosts, CA propia, DNS especial,
aplicaciones auxiliares o VPN. Se conserva la prohibición de la CA expresamente
excluida, freemium, pagos presentes/futuros, tarjetas y facturación.

Se evaluó como combinación concreta un subdominio gratuito deSEC/dedyn.io y TLS
ACME de Google Public CA, con actualización DNS y renovación ejecutadas en la PC.
Es una combinación investigada y **rechazada para integración**, no una propuesta
aprobada ni una asignación obtenida. No se comprobó disponibilidad registral ni se
solicitó `learngraphicsprogramming.dedyn.io`.

| Parte | Evidencia oficial actual | Resultado bajo las condiciones exigidas |
|---|---|---|
| Nombre deSEC/dedyn.io | Servicio gratuito; el aviso vigente suspende nuevas asignaciones `.dedyn.io` hasta nuevo aviso. | No se puede dar por obtenido un nombre nuevo. |
| HTTPS Google Public CA | Certificados públicos mediante ACME, uso local posible y emisión actualmente sin cargo. | CP/CPS 6.10 §9.1.1 permite cargos de emisión, gestión y renovación. No acredita gratuidad futura. |
| Conectividad | PC con IPv4 privada e IPv6 global candidata, firewall activo. | WAN IPv4/CGNAT, entrada del router y acceso externo no comprobados. |
| Continuidad | ACME y DNS dinámico permiten automatización técnica. | No existe automatización integrada y no corrigen las carencias de asignación/condiciones del proveedor. |

No procede pedir autorización para crear esas cuentas o abrir la red como si la
arquitectura hubiera pasado la condición económica.

## Condiciones verificadas del nombre

[deSEC](https://desec.io/) publica DNS gratuito para todos. El [registro dedyn.io](https://desec.io/signup?domainType=dynDNS)
describe un nombre por usuario, pensado para conexiones residenciales de dirección
cambiante y sin delegación externa. Sus [términos](https://desec.io/terms) no aportan
una prohibición expresa del uso comercial, pero permiten limitar o desactivar
cuentas por carga/costes extraordinarios y no garantizan disponibilidad. Los
nombres sin actualizaciones durante seis meses requieren confirmar el uso tras
el aviso; también hay obligaciones de atender comunicaciones de la cuenta.

La aplicación oficial publicada contiene el aviso `news-20260921001`, con inicio
21-09-2026 y sin fecha de fin, que suspende nuevas asignaciones `.dedyn.io`. Se
leyó el HTML y el [asset oficial actual](https://desec.io/assets/index-vfZhJPWl.js)
sin crear cuenta ni aceptar acuerdos. SHA-256 del asset leído:
`c2672f4f914c5379bd53c26b65643d531abffc7af569c2b4cec9806c10671c9c`.
Los assets cambian; el hash identifica la evidencia de esta revisión, no una API
estable para el futuro.

La [documentación de límites](https://desec.readthedocs.io/en/latest/rate-limits.html)
publica, entre otros, 2 actualizaciones DDNS por 2 minutos, 300 modificaciones de
RRsets/día por dominio y 2.000 operaciones autenticadas/día. Son cuotas de gestión,
**no un límite de 2.000 visitantes**. No se presenta un valor de administración
como cupo comercial de usuarios ni se promete capacidad ilimitada.

Otros nombres contrastados no proporcionaron evidencia suficiente para aprobar
el conjunto: [dynv6](https://dynv6.com/) anuncia gratuidad IPv4/IPv6 para todos,
pero advierte que carece de SLA/protección empresarial y pide no usarlo para
servicios críticos; no se acreditó un compromiso de continuidad gratuita que
cubra este diseño. [EU.org](https://nic.eu.org/policy.html) contempla sitios
comerciales pequeños como último recurso, requiere aprobación/delegación y DNS
aparte; eso no acredita el crecimiento comercial sostenido solicitado.

## Condiciones verificadas del certificado

La [guía oficial de Google Public CA](https://docs.cloud.google.com/certificate-manager/docs/public-ca-tutorial)
declara solicitudes sin cargo. Requiere proyecto, API habilitada, rol apropiado,
EAB y registro ACME. El EAB se utiliza en siete días para una cuenta; la cuenta
resultante no caduca. Borrar el proyecto impide emitir/renovar sus certificados.
La clave privada del servidor puede permanecer local: ACME envía claves públicas
y demostraciones de control, no exige entregar la clave privada del servidor.

Su [documentación](https://docs.cloud.google.com/certificate-manager/docs/public-ca)
contempla instalaciones locales y certificados de confianza pública. La
[documentación de confianza](https://developers.google.com/public-key-infrastructure/faq/root-program-inclusion)
identifica los programas raíz, incluido Chrome. Eso acredita la posibilidad
técnica, no una prueba Chrome ejecutada contra nuestro menú ni una aprobación de
sus condiciones económicas.

El [CP/CPS TLS 6.10](https://pki.goog/repo/cp-cps-tls/6.10/GTS-CP-CPS-TLS.html),
identificado como vigente en el [índice oficial](https://pki.goog/repo/repo.json),
permite cobrar emisión, gestión y renovación en §9.1.1; §9.7 no garantiza
disponibilidad y permite modificar/discontinuar; §9.12 contempla modificaciones.
Esto basta para **no acreditar la continuidad sin pagos futuros exigida**, aunque
la guía actual diga sin cargo. No significa que se haya cobrado algo aquí.

Se leyó también el [Markdown oficial equivalente](https://pki.goog/repo/cp-cps-tls/6.10/GTS-CP-CPS-TLS.md)
por HTTPS validado: SHA-256
`2b0224780ad475ab47f7b50778630adb914e1ce41e5677ca900a5b66cb1e896a`.
El [acuerdo de suscriptor 1.4](https://pki.goog/repo/sa/1.4/GTS-SA.pdf) debe
aceptarse para solicitar certificados y contiene terminación/modificaciones.
No se aceptó ese acuerdo. La guía ACME directa no enumera facturación como
prerrequisito: **no se afirma que obligue a activarla**; tampoco se confunde con
otros productos facturables de Certificate Manager.

Las [cuotas Public CA](https://docs.cloud.google.com/certificate-manager/docs/quotas#public_ca_request_quotas)
incluyen 100 pedidos de certificados/hora/proyecto y límites de cuentas/desafíos.
Son límites de emisión, no de visitas: el crecimiento de visitantes no implica
por sí solo necesitar más certificados o un plan superior. El bloqueo económico
indicado es la reserva de cargos y continuidad, no esa inferencia incorrecta.

Como contraste, [SSL.com Free DV](https://www.ssl.com/products/website-security/tls-ssl/single-domain/free-dv/)
sí anuncia expresamente gratuidad permanente y renovaciones gratuitas, un FQDN y
90 días, junto con opciones de pago superiores. No se oculta esa promesa ni se
afirma que hoy cobre la renovación. Su [acuerdo](https://legal.ssl.com/documents/SSLcom-Subscriber-Agreement.pdf)
§7.2 permite discontinuar productos; no acredita la continuidad del conjunto
exigido, ni resuelve la falta de un nombre compatible. Un FQDN no es un cupo de
visitantes y vender una app no implica técnicamente necesitar OV/EV. No se integra
como alternativa ni se supone que luego se pagará o cambiará de proveedor.
Tampoco se usa una prueba temporal o un plan freemium como solución definitiva.

## Red y continuidad de nuestra infraestructura

Diagnóstico de solo lectura, 2026-10-19 14:15 UTC: Ethernet2, perfil Public,
IPv4 `198.51.100.10/24` DHCP, gateway `198.51.100.1`; IPv6 candidata
`2001:db8:feed::10/64`, más una dirección temporal diferente de
la revisión anterior; rutas por defecto IPv4/IPv6 presentes. Firewall efectivo
activo con entrada Block. Sin listeners443 ni proceso de demo activo detectado.
Sin servicios/tareas ServerTec nuevos ni encaminamiento portproxy.

La IPv4 pública/WAN y CGNAT, ACL/NAT del router y entrada externa siguen sin
determinar. Una IPv6 global local no demuestra recepción ni acceso de visitantes
solo IPv4. No se abren puertos, cambia router/firewall o usa un túnel para suplirlo.
No se pide el router o la IP de cada visitante.

La continuidad pública **no está implementada ni aprobada**:

- Reiniciar PC: el listener actual en primer plano no vuelve a arrancar solo.
- Reiniciar router/cambiar IP: no hay actualizador A/AAAA ni dirección pública
  estable acreditada. La asociación pública tendría que actualizarse en nuestra
  infraestructura sin intervención del visitante, con reintentos y alerta de fallo.
- Certificado: la PKI privada conservada vence el 26-10-2026; no es un certificado
  público ni se cambia para simularlo. La futura renovación pública tendría que
  comprobar cadena/nombre/vigencia y sustituir archivos de forma atómica, mantener
  rollback y avisar antes de vencer si falla. No puede suplirse con una CA propia
  en el visitante ni con ignorar errores TLS.
- Capacidad: la demo tiene límites globales de 240 peticiones/minuto y 16
  concurrentes. Son límites propios, no cuotas del DNS/CA. PC, conexión, energía
  y mitigación de ataques son recursos finitos; no se ha medido capacidad comercial.

Un servicio/tarea local, cliente DDNS o cliente ACME no resuelve la falta de
condiciones verificadas; por ello no se instala ninguno como provisional.

## Cambios, pruebas y operación

Solo se actualizan README.md, DEMO-WEB.md, RESULTADOS.md y este informe. Código,
dependencias, certificados, claves, backend y datos existentes se conservan.
No se asignó un nombre público, registró cuenta, solicitó certificado, aceptó
acuerdo ni activó facturación. No hay dependencia externa nueva integrada.

Nuevas comprobaciones en esta ejecución, con recursos temporales:

- Demo: **171 passed**, 8,27 s, usando `Demo-Web.ps1 -Accion Pruebas`.
- Backend original: **AutoPrueba 9/9**, HTTPS/SQLite reales de QA; estado temporal
  eliminado. No se abrieron cuentas/saldos/base reales.
- Diagnóstico PowerShell de solo lectura: correcto; sin avisos de lectura ni
  confirmación externa. Las reglas candidatas no se presentan como permiso Python.

No se repiten cifras históricas como nueva ejecución completa. No se probaron
Chrome Windows/Android desde Internet, reinicios públicos ni renovación pública.

Comandos locales de QA, desde cualquier consola:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File 'E:\PersonalFiles\Projects\ServerTec\Demo-Web.ps1' -Accion Pruebas
powershell -NoProfile -ExecutionPolicy Bypass -File 'E:\PersonalFiles\Projects\ServerTec\ServerTec.ps1' -Accion AutoPrueba
powershell -NoProfile -ExecutionPolicy Bypass -File 'E:\PersonalFiles\Projects\ServerTec\Diagnostico-Demo-Externa.ps1'
```

El arranque/comprobación de la demo privada conservada sigue en DEMO-WEB.md,
marcado como QA interna histórica; detener con Ctrl+C solo su consola. No son
comandos de una publicación pública aprobada. Al no aplicar configuración nueva
no hay reglas/cuentas/servicios de esta evaluación que revertir; no borrar las
claves ni el material privado existente para retirar esta investigación.

**Funciona localmente:** sí, probado; listener actualmente detenido.
**Preparado para prueba externa pública:** no.
**Confirmado públicamente en Chrome sin preparar al visitante:** no.

# ES-SIFEN-000 — Requisitos Generales

## 1. Propósito
Definir el alcance, objetivos, dependencias y requisitos generales del módulo de Facturación Electrónica del sistema comercial, integrado con SIFEN/e-Kuatia de la DNIT.

## 2. Alcance
El módulo deberá cubrir:
- Preparación de Documentos Electrónicos (DE).
- Generación y validación XML.
- Generación del CDC.
- Firma digital.
- Transmisión a SIFEN.
- Consulta de resultados.
- Gestión de eventos.
- Generación de KuDE y QR.
- Persistencia y auditoría.
- Manejo de errores, reintentos y contingencia.
- Operación en ambiente de pruebas y producción.

## 3. Fuentes normativas y técnicas
La implementación debe basarse en la documentación oficial vigente de la DNIT:
- Manual Técnico SIFEN Versión 150.
- Notas Técnicas vigentes asociadas a V150.
- Estructura XML de DE.
- Esquemas XSD de DE.
- Tablas y codificaciones.
- Guía de Pruebas para e-Kuatia.
- Recomendaciones para servicios asíncronos.

**Regla:** si una nota técnica vigente modifica una regla del Manual V150, prevalece la disposición vigente comunicada por DNIT.

## 4. Arquitectura objetivo
El sistema base será una aplicación de escritorio/local:
- Python 3.13.
- PySide6.
- gRPC para comunicación interna.
- PostgreSQL 17.
- Sin servidor HTTP público.
- Internet únicamente para comunicación con servicios externos autorizados, principalmente SIFEN.

## 5. Requisitos funcionales generales
- RF-000-01: Configurar datos tributarios del emisor.
- RF-000-02: Configurar establecimiento y punto de expedición.
- RF-000-03: Crear DE a partir de una operación comercial.
- RF-000-04: Generar XML conforme al XSD vigente.
- RF-000-05: Generar CDC conforme al Manual Técnico.
- RF-000-06: Firmar digitalmente el DE.
- RF-000-07: Transmitir el DE a SIFEN.
- RF-000-08: Registrar respuestas y estados.
- RF-000-09: Generar KuDE para documentos aprobados según corresponda.
- RF-000-10: Registrar eventos.
- RF-000-11: Mantener trazabilidad y auditoría.
- RF-000-12: Permitir reintentos controlados.
- RF-000-13: Operar con mecanismos de contingencia definidos por SIFEN.

## 6. Requisitos no funcionales
- Integridad: ningún XML transmitido podrá alterarse posteriormente.
- Trazabilidad: cada operación deberá poder reconstruirse.
- Seguridad: certificados, claves y CSC nunca deberán quedar expuestos en logs.
- Disponibilidad: la emisión comercial no deberá perder información por fallos temporales de Internet.
- Idempotencia: los reintentos no deberán producir duplicados lógicos.
- Auditabilidad: registrar usuario, fecha, operación y resultado.
- Mantenibilidad: separar dominio tributario, transporte SIFEN y UI.

## 7. Criterios de aceptación
El módulo no se considerará listo para producción hasta:
1. Validar XML con los XSD oficiales.
2. Completar las pruebas requeridas por DNIT.
3. Confirmar firma digital.
4. Confirmar transmisión y consulta de resultados.
5. Validar generación de KuDE/QR.
6. Validar errores y reintentos.
7. Validar conservación de evidencias.
8. Completar el proceso administrativo de habilitación correspondiente.

## 8. Fuera de alcance
- Interpretación tributaria personalizada.
- Sustitución de trámites administrativos del contribuyente.
- Custodia externa del certificado.
- Integraciones con terceros no requeridas por SIFEN.

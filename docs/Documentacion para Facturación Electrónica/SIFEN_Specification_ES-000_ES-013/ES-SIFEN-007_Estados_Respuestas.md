# ES-SIFEN-007 — Estados y Respuestas

## 1. Objetivo
Normalizar las respuestas de SIFEN y separar estados técnicos de estados tributarios.

## 2. Estados internos sugeridos
- DRAFT
- VALIDATING
- XML_READY
- SIGNED
- QUEUED
- SENT
- PROCESSING
- APPROVED
- REJECTED
- ERROR_RETRYABLE
- ERROR_FINAL
- CANCELLED
- EVENT_PENDING

Los nombres son internos y no sustituyen códigos oficiales de SIFEN.

## 3. Respuesta SIFEN
Persistir:
- código;
- mensaje;
- fecha/hora;
- identificador de transacción/lote;
- CDC;
- tipo de respuesta;
- detalle de errores;
- documento relacionado.

## 4. Rechazos
Un rechazo debe:
- conservar el XML enviado;
- conservar la respuesta;
- identificar primer error y demás detalles disponibles;
- impedir tratar el documento como DTE aprobado;
- permitir corrección y nueva emisión según corresponda.

## 5. Aprobación
Al aprobar:
- marcar como DTE;
- registrar fecha/hora;
- guardar respuesta;
- habilitar generación/entrega del KuDE;
- habilitar eventos permitidos.

## 6. Regla de negocio crítica
Un DE firmado no debe considerarse automáticamente DTE. La DNIT indica que el DE adquiere naturaleza de DTE cuando es transmitido, validado y aprobado por SIFEN.

## 7. Criterios de aceptación
Todo estado debe tener:
- transición válida;
- responsable;
- timestamp;
- evidencia;
- regla de transición.

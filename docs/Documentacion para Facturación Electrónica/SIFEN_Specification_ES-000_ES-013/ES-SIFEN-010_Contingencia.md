# ES-SIFEN-010 — Contingencia

## 1. Objetivo
Garantizar continuidad operativa ante fallas de Internet, SIFEN, certificados o componentes locales, sin inventar procedimientos tributarios no contemplados oficialmente.

## 2. Principio
La contingencia debe implementarse exactamente según las reglas vigentes de DNIT/SIFEN para el tipo de operación.

## 3. Arquitectura local
```text
Venta
 ↓
Outbox local
 ↓
Cola de facturación
 ↓
Conectividad disponible?
 ├─ Sí → SIFEN
 └─ No → espera/reintento según regla aplicable
```

## 4. Outbox
Cada operación deberá persistirse antes de intentar comunicación externa.

Campos:
- id;
- documento_id;
- tipo;
- estado;
- intentos;
- next_attempt_at;
- last_error;
- created_at;
- processed_at.

## 5. Reintentos
Clasificar:
- timeout;
- error DNS/red;
- indisponibilidad remota;
- rechazo tributario;
- error de autenticación;
- error de XML.

Solo errores transitorios deben reintentarse automáticamente.

## 6. Protección contra duplicados
Usar:
- clave interna de idempotencia;
- CDC/correlación;
- registro de intentos;
- consulta previa cuando sea necesario.

## 7. Restauración
Cuando vuelva la conectividad:
1. detectar documentos pendientes;
2. validar integridad;
3. enviar según reglas;
4. consultar resultado;
5. actualizar estado;
6. generar KuDE si corresponde.

## 8. Regla crítica
No implementar "facturas offline" con una numeración o procedimiento inventado. Cualquier modalidad de contingencia tributaria debe derivarse de la normativa y Manual Técnico vigentes.

## 9. Criterios de aceptación
Simular:
- Internet caída;
- SIFEN no disponible;
- timeout;
- recuperación;
- reintento;
- respuesta duplicada;
- rechazo posterior.

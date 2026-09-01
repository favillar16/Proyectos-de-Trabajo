# ES-SIFEN-012 — Estrategia de Pruebas

## 1. Objetivo
Definir las pruebas técnicas y funcionales necesarias antes de producción.

## 2. Fuentes
La Guía de Pruebas oficial de e-Kuatia y la documentación técnica vigente de DNIT son la referencia para las pruebas requeridas.

## 3. Niveles
### Unitarias
- CDC.
- redondeos.
- impuestos.
- validaciones.
- serialización.
- QR.
- estados.

### Integración
- XML + XSD.
- firma.
- SIFEN TEST.
- consultas.
- eventos.

### End-to-end
Venta → DE → XML → firma → SIFEN → DTE → KuDE.

### Resiliencia
- Internet caída.
- timeout.
- respuestas tardías.
- duplicados.
- reinicio de aplicación.
- corrupción de cola.

## 4. Matriz mínima
| Caso | Resultado esperado |
|---|---|
| XML válido | Acepta validación local |
| XML inválido | Rechazo antes de envío |
| Firma válida | Verificación OK |
| Firma inválida | Bloqueo |
| DE aprobado | Estado DTE |
| DE rechazado | Estado REJECTED |
| Timeout | Reintento controlado |
| QR válido | Datos consultables |
| Receptor inválido | Error según regla |
| Totales incorrectos | Bloqueo |
| Certificado vencido | Bloqueo |

## 5. Pruebas con SIFEN
Separar:
- TEST;
- PRODUCCIÓN.

Nunca usar producción como entorno de experimentación.

## 6. Evidencias
Guardar:
- caso;
- fecha;
- versión;
- entrada;
- resultado;
- respuesta SIFEN;
- responsable;
- evidencia de aprobación.

## 7. Criterios de salida
No pasar a producción con:
- errores críticos;
- firma inválida;
- discrepancias de totales;
- fallas de persistencia;
- pérdida de trazabilidad;
- reintentos duplicadores.

## 8. Automatización
El proyecto deberá incluir:
```text
tests/
├── unit/
├── integration/
├── sifen/
├── xml/
├── signature/
├── kude/
└── resilience/
```

# ES-SIFEN-002 — Documentos Electrónicos

## 1. Objetivo
Definir la representación interna de los documentos electrónicos y su relación con las operaciones comerciales.

## 2. Conceptos
- DE: Documento Electrónico emitido y firmado digitalmente, pendiente de aprobación de SIFEN.
- DTE: Documento Electrónico transmitido, validado y aprobado por SIFEN.
- KuDE: representación gráfica del documento, conforme a las reglas aplicables.

## 3. Tipos
El diseño deberá permitir incorporar los tipos de DE contemplados por la versión vigente del Manual Técnico, sin acoplar la lógica de negocio a un único documento.

Como mínimo, el modelo deberá estar preparado para:
- Factura Electrónica.
- Factura de Exportación Electrónica.
- Autofactura Electrónica.
- Nota de Crédito Electrónica.
- Nota de Débito Electrónica.
- Nota de Remisión Electrónica.
- Otros documentos incorporados oficialmente.

## 4. Modelo de documento
Campos conceptuales:
- Identificador interno.
- Tipo de DE.
- Establecimiento.
- Punto de expedición.
- Número.
- Fecha/hora.
- Emisor.
- Receptor.
- Moneda.
- Condición de operación.
- Ítems.
- Descuentos/recargos.
- Impuestos.
- Totales.
- CDC.
- Estado SIFEN.
- XML.
- Firma.
- Respuesta.

## 5. Ciclo de vida
BORRADOR → VALIDANDO → XML_GENERADO → FIRMADO → ENVIADO → PROCESANDO → APROBADO/RECHAZADO.

Eventos posteriores se gestionarán independientemente.

## 6. Integridad
Los valores comerciales usados para generar el XML deben conservarse y poder compararse con el XML transmitido.

## 7. Idempotencia
Cada DE debe poseer una identidad interna estable y una estrategia de correlación con SIFEN para evitar reenvíos accidentales.

## 8. Criterios de aceptación
Cada tipo de documento soportado deberá contar con:
- DTO interno.
- Reglas de validación.
- Serializador XML.
- Pruebas unitarias.
- Casos válidos e inválidos.
- Mapeo a KuDE cuando corresponda.

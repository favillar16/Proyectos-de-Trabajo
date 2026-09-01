# ES-SIFEN-001 — Modelo Tributario y Datos del Emisor

## 1. Objetivo
Definir el modelo de información tributaria necesario para emitir documentos electrónicos válidos.

## 2. Datos del contribuyente
El sistema deberá contemplar como mínimo:
- RUC.
- Razón social / nombre.
- Nombre comercial cuando corresponda.
- Actividades económicas relevantes.
- Régimen y datos tributarios aplicables.
- Datos de contacto requeridos.
- Estado de habilitación del facturador electrónico.

## 3. Establecimientos
Cada establecimiento deberá registrar:
- Identificador/código correspondiente.
- Dirección.
- Departamento.
- Distrito.
- Ciudad/localidad.
- Datos geográficos requeridos por las tablas oficiales.
- Estado activo/inactivo.

## 4. Puntos de expedición
Cada punto deberá asociarse a un establecimiento y contener:
- Código del punto.
- Estado.
- Tipos de documentos autorizados.
- Numeración controlada.

## 5. Timbrado
El modelo deberá permitir almacenar:
- Número de timbrado.
- Fecha de inicio de vigencia.
- Fecha de vencimiento si corresponde.
- Establecimiento.
- Punto de expedición.
- Tipos de documentos.
- Estado.

No se deberá generar un documento fuera de los parámetros tributarios configurados.

## 6. Receptores
Debe soportar:
- Receptor con RUC.
- Receptor sin RUC/consumidor final, según las reglas vigentes.
- Identificación extranjera cuando corresponda.
- Datos fiscales y comerciales requeridos por el tipo de documento.

## 7. Impuestos
El modelo debe representar, como mínimo, los conceptos que correspondan al documento:
- Tipo de impuesto.
- Tasa.
- Base imponible.
- Valor del impuesto.
- Exoneración/no gravado según catálogo y reglas vigentes.
- Totales y subtotales.

Los códigos no deberán estar hardcodeados sin una fuente versionada.

## 8. Catálogos
Los catálogos DNIT deberán persistirse con:
- Código.
- Descripción.
- Versión/fuente.
- Vigencia.
- Fecha de actualización.

## 9. Validaciones
Antes de generar el XML:
- RUC válido según reglas aplicables.
- Establecimiento activo.
- Punto de expedición válido.
- Timbrado compatible.
- Numeración válida.
- Totales consistentes.
- Impuestos consistentes.
- Datos obligatorios presentes.

## 10. Criterios de aceptación
Una factura no podrá avanzar al proceso de firma si falla una validación tributaria estructural.

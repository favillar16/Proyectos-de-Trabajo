# ES-SIFEN-003 — Estructura XML

## 1. Objetivo
Establecer el proceso para construir XML de DE conforme a la estructura oficial.

## 2. Fuente de verdad
La estructura no deberá inferirse de ejemplos aislados.
Se utilizarán:
1. Manual Técnico V150.
2. Notas Técnicas vigentes.
3. Estructura xml_DE oficial.
4. XSD oficial.
5. Tablas y codificaciones oficiales.

## 3. Pipeline
Modelo de dominio
→ DTO tributario
→ validación de negocio
→ serialización XML
→ validación XSD
→ generación/fijación de CDC cuando corresponda
→ firma digital
→ validación final
→ transmisión.

## 4. Reglas
- Respetar namespaces.
- Respetar orden de elementos exigido por XSD.
- Respetar cardinalidad.
- Respetar tipos de datos.
- Respetar longitudes.
- Respetar precisión decimal.
- No introducir campos no autorizados.
- No eliminar campos obligatorios.
- Aplicar codificaciones oficiales.

## 5. Validación
Debe existir un validador local contra XSD antes de transmitir.

Resultado:
- VALID_XML.
- INVALID_XML con lista de errores.

## 6. Versionado
El componente XML debe registrar:
- versión del Manual.
- versión de XSD.
- versión de catálogos.
- versión de notas técnicas aplicadas.

## 7. Artefactos
Conservar:
- XML original generado.
- XML firmado.
- checksum/hash interno del archivo.
- fecha de generación.
- versión de especificación.

## 8. Criterios de aceptación
Ningún DE podrá transmitirse si no supera:
- validación de dominio,
- validación estructural,
- validación XSD,
- validaciones de integridad previas a firma.

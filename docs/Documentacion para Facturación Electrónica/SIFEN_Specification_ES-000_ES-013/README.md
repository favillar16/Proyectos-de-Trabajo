# SIFEN Integration Specification

Especificación inicial para integrar un sistema comercial de escritorio con la Facturación Electrónica e-Kuatia/SIFEN de la DNIT Paraguay.

## Documentos
- ES-SIFEN-000 — Requisitos Generales
- ES-SIFEN-001 — Modelo Tributario
- ES-SIFEN-002 — Documentos Electrónicos
- ES-SIFEN-003 — Estructura XML
- ES-SIFEN-004 — CDC
- ES-SIFEN-005 — Firma Digital
- ES-SIFEN-006 — Comunicación SIFEN
- ES-SIFEN-007 — Estados y Respuestas
- ES-SIFEN-008 — KuDE y QR
- ES-SIFEN-009 — Eventos
- ES-SIFEN-010 — Contingencia
- ES-SIFEN-011 — Seguridad
- ES-SIFEN-012 — Pruebas
- ES-SIFEN-013 — Producción

## Fuente oficial
La implementación debe contrastarse permanentemente con la documentación vigente publicada por DNIT/e-Kuatia.

Referencia oficial:
- Documentación Técnica e-Kuatia.
- Manual Técnico V150.
- Notas Técnicas vigentes V150.
- Estructura XML.
- XSD.
- Tablas y Codificaciones.
- Guía de Pruebas.

## Regla de oro
Estos documentos son la especificación de ingeniería del proyecto, no sustituyen la normativa tributaria ni la documentación oficial DNIT. Cuando exista una diferencia, debe actualizarse la especificación del proyecto para reflejar la fuente oficial vigente.

## Stack objetivo del proyecto
- Python 3.13
- PySide6
- gRPC
- PostgreSQL 17
- Aplicación local/desktop
- SIFEN como servicio externo tributario

## Estructura sugerida del módulo
```text
sifen/
├── domain/
├── application/
├── infrastructure/
│   ├── xml/
│   ├── signature/
│   ├── sifen/
│   ├── kude/
│   └── persistence/
├── tests/
└── docs/
```

## Dependencias externas que deben versionarse
No copiar manualmente tablas o XSD sin registrar su versión y origen. Mantener:
- versión del Manual;
- notas técnicas aplicadas;
- versión de XSD;
- checksum cuando DNIT lo publique;
- fecha de descarga;
- responsable de actualización.

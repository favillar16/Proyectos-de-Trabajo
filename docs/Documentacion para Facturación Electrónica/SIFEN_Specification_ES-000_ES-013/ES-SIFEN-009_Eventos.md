# ES-SIFEN-009 — Eventos

## 1. Objetivo
Gestionar los eventos asociados a DE/DTE.

## 2. Concepto
Un evento es una ocurrencia registrada en SIFEN por el emisor, receptor, DNIT o automáticamente, que puede modificar o afectar el estado de un DE/DTE.

## 3. Diseño
Tabla `sifen_eventos`:
- id;
- documento_id;
- tipo_evento;
- actor;
- fecha_evento;
- estado;
- request;
- response;
- código;
- mensaje;
- usuario;
- correlación.

## 4. Arquitectura
```text
Documento
   ↓
Event Service
   ↓
Validación
   ↓
Generación XML/evento
   ↓
Firma si corresponde
   ↓
SIFEN
   ↓
Resultado
```

## 5. Reglas
Cada evento deberá:
- corresponder a un documento;
- cumplir las condiciones del Manual;
- registrar fecha/hora;
- conservar respuesta;
- impedir duplicación accidental.

## 6. Auditoría
Los eventos no deben eliminarse físicamente.
Usar auditoría/inactivación cuando corresponda.

## 7. Criterios de aceptación
Cada evento soportado debe tener:
- definición;
- precondiciones;
- payload;
- validaciones;
- respuesta esperada;
- pruebas positivas y negativas.

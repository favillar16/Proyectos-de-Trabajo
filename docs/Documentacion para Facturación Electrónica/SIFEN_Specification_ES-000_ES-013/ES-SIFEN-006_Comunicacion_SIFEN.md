# ES-SIFEN-006 — Comunicación con SIFEN

## 1. Objetivo
Definir el adaptador de comunicación entre el sistema local y los servicios de SIFEN.

## 2. Principio de diseño
La lógica de negocio no debe conocer detalles de SOAP/HTTP, endpoints, headers ni serialización de transporte.

## 3. Arquitectura
```text
Application Service
        ↓
SIFEN Gateway Interface
        ↓
SIFEN SOAP/Transport Adapter
        ↓
SIFEN
```

## 4. Capacidades
El adaptador deberá soportar los servicios definidos por la documentación vigente, incluyendo según corresponda:
- recepción de DE;
- recepción de lote;
- consulta de resultado de lote;
- consulta de DE;
- consulta de RUC;
- recepción de eventos.

## 5. Sincrónico y asíncrono
La solución deberá contemplar ambos patrones cuando el servicio correspondiente lo requiera.

Para operaciones asíncronas:
- registrar identificador de solicitud/lote;
- guardar fecha/hora;
- mantener estado PROCESSING;
- consultar resultado;
- correlacionar respuesta.

## 6. Reintentos
Implementar:
- timeout;
- backoff;
- máximo de reintentos;
- clasificación de errores transitorios/permanentes;
- idempotencia.

## 7. Observabilidad
Registrar:
- operación;
- timestamp;
- duración;
- correlación;
- código de respuesta;
- estado;
- error sanitizado.

No registrar XML completo ni secretos indiscriminadamente en logs.

## 8. Ambientes
Configurar separadamente:
- TEST.
- PRODUCCIÓN.

Nunca permitir que credenciales de producción sean usadas accidentalmente en TEST.

## 9. Criterios de aceptación
El adaptador debe poder probarse mediante mocks/fakes sin depender de SIFEN real.

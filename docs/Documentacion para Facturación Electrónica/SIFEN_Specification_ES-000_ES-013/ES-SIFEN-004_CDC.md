# ES-SIFEN-004 — Código de Control (CDC)

## 1. Objetivo
Implementar el cálculo y manejo del Código de Control de 44 dígitos conforme al Manual Técnico vigente.

## 2. Regla crítica
No implementar el algoritmo a partir de una explicación secundaria.
La fuente de verdad será la sección correspondiente del Manual Técnico V150 y sus Notas Técnicas vigentes.

## 3. Componentes
El servicio CDC deberá:
- Recibir los campos requeridos.
- Normalizar los valores según las reglas oficiales.
- Construir la secuencia base.
- Aplicar el algoritmo de control indicado por DNIT.
- Generar el dígito de control.
- Retornar el CDC completo.
- Validar longitud y formato.

## 4. Características
El CDC es un identificador numérico de 44 dígitos asociado a un DE y permite identificarlo de forma única conforme a las reglas de SIFEN.

## 5. Servicio
Interfaz conceptual:

```text
generate_cdc(document_data) -> CDCResult
validate_cdc(document_data, cdc) -> ValidationResult
```

## 6. Pruebas
Debe incluir:
- casos oficiales disponibles;
- valores mínimos/máximos;
- cambios de establecimiento;
- cambios de punto;
- cambios de número;
- distintos tipos de documento;
- casos inválidos.

## 7. Persistencia
Guardar:
- CDC.
- fecha de generación.
- versión de algoritmo/especificación.
- referencia al DE.

## 8. Criterios de aceptación
El resultado debe coincidir con los casos de referencia oficiales y ser rechazado si no cumple las condiciones de longitud/formato.

# ES-SIFEN-008 — KuDE y Código QR

## 1. Objetivo
Generar la representación gráfica del DTE conforme a las especificaciones oficiales.

## 2. KuDE
El generador deberá:
- seleccionar plantilla según tipo de documento;
- incluir datos exigidos;
- respetar formatos;
- incluir CDC;
- incluir QR cuando corresponda;
- soportar múltiples páginas cuando aplique;
- evitar información que no forme parte del XML firmado salvo excepciones autorizadas.

## 3. QR
El QR será generado según el Manual Técnico y deberá permitir la consulta/validación definida por SIFEN.

## 4. CSC
El Código de Seguridad del Contribuyente deberá tratarse como secreto.
Nunca:
- imprimirlo en logs;
- mostrarlo en pantalla sin necesidad;
- guardarlo sin protección.

## 5. Validaciones
Antes de entregar:
- CDC correcto;
- QR decodificable;
- datos del KuDE coinciden con el XML;
- formato correcto;
- documento aprobado cuando la regla de entrega así lo exija.

## 6. Salidas
- PDF.
- impresión.
- archivo para envío al cliente.

## 7. Criterios de aceptación
El KuDE deberá coincidir con las exigencias del Manual Técnico y ser verificable mediante QR/CDC conforme a los mecanismos de DNIT.

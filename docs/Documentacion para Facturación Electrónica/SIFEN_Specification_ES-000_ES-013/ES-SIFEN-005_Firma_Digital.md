# ES-SIFEN-005 — Firma Digital

## 1. Objetivo
Definir la firma digital del DE antes de su transmisión a SIFEN.

## 2. Requisitos
El sistema deberá utilizar un certificado digital válido y compatible con los requisitos establecidos por DNIT para facturación electrónica.

## 3. Gestión del certificado
Registrar:
- certificado público;
- emisor del certificado;
- titular;
- RUC asociado;
- vigencia;
- huella/fingerprint;
- ubicación segura del material privado;
- estado.

La clave privada nunca deberá almacenarse en texto plano dentro de la base de datos.

## 4. Flujo
XML DE
→ canonicalización/proceso requerido
→ firma digital según especificación
→ XML firmado
→ validación de firma
→ transmisión.

## 5. Seguridad
Prohibido:
- registrar claves privadas en logs;
- incluir contraseñas en código;
- enviar secretos a agentes de IA;
- almacenar certificados privados en repositorios;
- mostrar secretos en excepciones.

## 6. Errores
- certificado vencido;
- certificado no corresponde al RUC;
- clave incorrecta;
- algoritmo no compatible;
- XML alterado;
- firma inválida.

## 7. Criterios de aceptación
El XML firmado deberá:
- ser verificable;
- mantener integridad;
- cumplir la estructura exigida;
- ser aceptado por las validaciones del ambiente de pruebas SIFEN.

## 8. Auditoría
Registrar únicamente metadatos seguros:
- fingerprint;
- fecha;
- resultado;
- versión de librería;
- usuario/proceso.
Nunca registrar la clave privada.

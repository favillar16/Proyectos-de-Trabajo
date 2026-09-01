# ES-SIFEN-011 — Seguridad

## 1. Objetivo
Proteger información tributaria, certificados, credenciales y documentos.

## 2. Activos críticos
- Certificado digital.
- Clave privada.
- Contraseña/PIN.
- CSC.
- XML firmado.
- Respuestas SIFEN.
- Datos de clientes.
- Auditoría.

## 3. Principios
- mínimo privilegio;
- separación de responsabilidades;
- cifrado de secretos;
- logs sanitizados;
- control de acceso;
- trazabilidad;
- backups protegidos.

## 4. Certificados
Preferir almacén seguro del sistema operativo o mecanismo equivalente.
Si se utiliza archivo:
- permisos restrictivos;
- cifrado/protección;
- ruta fuera del código fuente;
- backup seguro;
- nunca subirlo a repositorios.

## 5. Roles
Mínimamente:
- Administrador.
- Facturación.
- Caja.
- Auditor/consulta.

Las operaciones sensibles deben requerir permisos adecuados.

## 6. Logs
Nunca registrar:
- claves privadas;
- contraseñas;
- CSC;
- tokens secretos.

Sanitizar XML si contiene información sensible.

## 7. Base de datos
- credenciales PostgreSQL seguras;
- conexiones restringidas;
- backups cifrados;
- auditoría;
- separación de cuentas técnicas.

## 8. Agentes de IA
Los agentes no deberán recibir:
- certificados privados;
- contraseñas;
- CSC;
- datos reales innecesarios.

Usar fixtures/anónimos para pruebas.

## 9. Criterios de aceptación
Realizar revisión de:
- secretos;
- permisos;
- logs;
- backups;
- acceso por rol;
- configuración de producción.

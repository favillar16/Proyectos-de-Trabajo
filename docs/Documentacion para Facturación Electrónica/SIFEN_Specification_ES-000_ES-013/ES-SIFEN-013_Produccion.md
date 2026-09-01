# ES-SIFEN-013 — Paso a Producción

## 1. Objetivo
Definir el checklist técnico y operativo para habilitar facturación electrónica real.

## 2. Requisitos administrativos
Confirmar con el contribuyente y DNIT:
- RUC activo;
- habilitación correspondiente;
- establecimiento/punto de expedición;
- certificado digital;
- timbrado;
- CSC;
- pruebas requeridas completadas;
- condiciones de producción autorizadas.

## 3. Configuración de producción
Separar completamente:
- endpoints;
- certificados;
- credenciales;
- parámetros;
- base de datos;
- logs;
- colas.

## 4. Checklist técnico
- [ ] XML XSD validado.
- [ ] CDC validado.
- [ ] Firma validada.
- [ ] Comunicación SIFEN validada.
- [ ] Consulta de resultados.
- [ ] Eventos soportados.
- [ ] KuDE.
- [ ] QR.
- [ ] Auditoría.
- [ ] Backups.
- [ ] Recuperación.
- [ ] Contingencia.
- [ ] Monitoreo.
- [ ] Control de permisos.

## 5. Despliegue
En el modelo local:
1. Instalar servidor PostgreSQL.
2. Instalar servicio/backend local.
3. Configurar certificados de producción.
4. Configurar parámetros tributarios.
5. Registrar establecimiento/punto.
6. Probar conectividad.
7. Emitir primer documento controlado.
8. Confirmar respuesta SIFEN.
9. Confirmar DTE.
10. Confirmar KuDE/QR.
11. Habilitar operación normal.

## 6. Rollback
Debe existir procedimiento para:
- detener emisión;
- conservar documentos pendientes;
- preservar evidencia;
- restaurar configuración;
- corregir versión;
- reanudar sin duplicados.

## 7. Monitoreo
Dashboard mínimo:
- documentos emitidos;
- aprobados;
- rechazados;
- pendientes;
- errores;
- reintentos;
- conectividad;
- certificado próximo a vencer.

## 8. Mantenimiento
Cuando DNIT publique nuevas Notas Técnicas o cambios de documentación:
1. analizar impacto;
2. actualizar especificación;
3. actualizar catálogos/XSD;
4. ejecutar pruebas;
5. registrar versión;
6. desplegar controladamente.

## 9. Criterio final
Producción solo se habilita cuando:
- requisitos administrativos están cumplidos;
- pruebas técnicas están aprobadas;
- seguridad está revisada;
- backup/recuperación está probado;
- personal operativo fue instruido;
- existe procedimiento de soporte.

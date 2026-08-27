# Periféricos — mapa general e impresoras

Qué hay conectado al sistema y para qué sirve cada cosa.

| Dispositivo | Para qué | Dónde se configura | Detalle |
|---|---|---|---|
| **Térmica FTX FTXP-80W** | Tickets y comprobantes de mostrador | `IMPRESORA_TERMICA_*` en `backend\.env` | §1 de este doc |
| **Impresora de facturas** | Comprobante fiscal | ⏳ **Pendiente** — todavía no se definió el equipo | — |

> **Nota (26/08/2026) — se retiró el sistema de código de barras.** El lector
> FTX LC123BH5 y la **Epson EcoTank L1250** ya no forman parte del sistema: se
> quitaron el escaneo, los códigos internos EAN-13 y la planilla de etiquetas.
> Los equipos siguen siendo del local, pero el software no los usa.
> Ver `docs/log_revisiones_tecnicas.md` → entrada del 2026-08-26.

Para probar la impresora:

```
cd backend
venv\Scripts\activate
python diagnostico_impresora.py
```

Lista las impresoras instaladas en Windows, avisa si el nombre del `.env` no
coincide con ninguna, y ofrece imprimir un ticket de prueba.

---

## 1. Térmica FTX FTXP-80W

Tickets y comprobantes de mostrador. Habla ESC/POS: el sistema le manda los
bytes crudos por la cola de Windows (`apps/caja/printer.py`). Se configura con
`IMPRESORA_TERMICA_NOMBRE` en `backend\.env` y se prueba con
`diagnostico_impresora.py`.

Mientras no esté conectada la impresora de facturas, la factura también sale
por acá. Sin timbrado cargado imprime la leyenda de que no es válida como
comprobante fiscal — ver `python manage.py verificar_fiscal`.

Los datos fiscales para cargar en el `.env` están en
`docs/carga_final/datos_fiscales.md`.

---

## 2. Problemas comunes

| Síntoma | Causa habitual |
|---|---|
| La térmica no aparece | El nombre del `.env` no coincide con el de Windows. `diagnostico_impresora.py` lista los nombres reales |
| La térmica no imprime | Ver `docs/checklist_entrega.md` → "La impresora no imprime" |
| La factura sale sin RUC ni timbrado | Faltan los `FISCAL_*` en el `.env`. Correr `python manage.py verificar_fiscal` |

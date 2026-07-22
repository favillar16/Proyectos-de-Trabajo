/**
 * ProductoForm
 * Formulario de 3 pasos para crear / editar productos con variantes e imágenes.
 *
 * Paso 0 — Datos generales del producto
 * Paso 1 — Variantes (color, dimensiones, precio, stock)
 * Paso 2 — Imágenes del producto
 */
import { useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  X, ChevronRight, ChevronLeft, Plus, Trash2,
  Upload, Image, Star, Loader2, Package,
  CheckCircle,
} from 'lucide-react'
import { productosApi } from '../../services/api'

const C = {
  sidebar:     '#453941',
  sidebarHover:'#362F31',
  gold:        '#B99C74',
  goldDark:    '#8a7355',
  goldMuted:   'rgba(185,156,116,0.10)',
  border:      '#e8e4df',
  bg:          '#ffffff',
  bgSec:       '#fafaf9',
  text:        '#1a1714',
  textSec:     '#6b6560',
  textMuted:   '#9e9892',
  danger:      '#9a3030',
  dangerBg:    '#fef0f0',
  success:     '#3d7a5a',
  successBg:   '#edf7f1',
}

// ─── Helpers de UI ────────────────────────────────────────────────────────────

function Field({ label, error, required, children, hint }) {
  return (
    <div style={{ marginBottom: '16px' }}>
      <label style={{
        display: 'block', fontSize: '12px', fontWeight: '500',
        color: error ? C.danger : C.textSec,
        marginBottom: '5px', letterSpacing: '0.02em',
      }}>
        {label}{required && <span style={{ color: C.gold, marginLeft: '3px' }}>*</span>}
      </label>
      {children}
      {hint && !error && (
        <p style={{ fontSize: '11px', color: C.textMuted, marginTop: '4px' }}>{hint}</p>
      )}
      {error && (
        <p style={{ fontSize: '11px', color: C.danger, marginTop: '4px' }}>{error}</p>
      )}
    </div>
  )
}

function Input({ error, ...props }) {
  return (
    <input
      {...props}
      style={{
        width: '100%', padding: '8px 11px',
        border: `1px solid ${error ? C.danger : C.border}`,
        borderRadius: '8px', fontSize: '13.5px',
        color: C.text, background: C.bg, outline: 'none',
        transition: 'border-color 120ms',
        ...props.style,
      }}
      onFocus={e => e.target.style.borderColor = error ? C.danger : C.gold}
      onBlur={e  => e.target.style.borderColor = error ? C.danger : C.border}
    />
  )
}

function Select({ error, children, ...props }) {
  return (
    <select
      {...props}
      style={{
        width: '100%', padding: '8px 11px',
        border: `1px solid ${error ? C.danger : C.border}`,
        borderRadius: '8px', fontSize: '13.5px',
        color: props.value ? C.text : C.textMuted,
        background: C.bg, outline: 'none', cursor: 'pointer',
      }}
    >
      {children}
    </select>
  )
}

function Textarea({ error, ...props }) {
  return (
    <textarea
      {...props}
      rows={3}
      style={{
        width: '100%', padding: '8px 11px',
        border: `1px solid ${error ? C.danger : C.border}`,
        borderRadius: '8px', fontSize: '13.5px',
        color: C.text, background: C.bg, outline: 'none',
        resize: 'vertical', fontFamily: 'inherit',
        transition: 'border-color 120ms',
      }}
      onFocus={e => e.target.style.borderColor = C.gold}
      onBlur={e  => e.target.style.borderColor = error ? C.danger : C.border}
    />
  )
}

function Toggle({ value, onChange, label }) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
      <div
        onClick={() => onChange(!value)}
        style={{
          width: '36px', height: '20px', borderRadius: '10px',
          background: value ? C.sidebar : C.border,
          border: value ? `1px solid ${C.gold}` : `1px solid ${C.border}`,
          position: 'relative', transition: 'all 150ms', flexShrink: 0,
        }}
      >
        <div style={{
          width: '14px', height: '14px', borderRadius: '50%',
          background: value ? C.gold : C.textMuted,
          position: 'absolute', top: '2px',
          left: value ? '19px' : '2px',
          transition: 'left 150ms, background 150ms',
        }} />
      </div>
      <span style={{ fontSize: '13px', color: C.textSec }}>{label}</span>
    </label>
  )
}

// ─── Paso 0: Datos del producto ───────────────────────────────────────────────

function PasoDatos({ form, errores, setField }) {
  const { data: categorias } = useQuery({
    queryKey: ['categorias'],
    queryFn: () => productosApi.categorias().then(r => r.data?.results || r.data || []),
  })
  const { data: marcas } = useQuery({
    queryKey: ['marcas'],
    queryFn: () => productosApi.marcas().then(r => r.data?.results || r.data || []),
  })
  const { data: tiposInst } = useQuery({
    queryKey: ['tipos-instalacion'],
    queryFn: () => productosApi.tiposInstalacion().then(r => r.data?.results || r.data || []),
  })

  const toggleTipoInstalacion = (id) => {
    const actual = form.tipos_instalacion_ids
    setField('tipos_instalacion_ids',
      actual.includes(id) ? actual.filter(x => x !== id) : [...actual, id]
    )
  }

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
        <Field label="Código"
          hint="Se genera automáticamente según la categoría">
          <div style={{
            height: '42px', display: 'flex', alignItems: 'center',
            padding: '0 12px', borderRadius: '9px',
            border: '1px dashed #d4bc98', background: 'rgba(185,156,116,0.08)',
            color: form.codigo ? '#1a1714' : '#9e9892',
            fontSize: '14px', fontFamily: 'monospace', letterSpacing: '0.02em',
          }}>
            {form.codigo || 'Se generará automáticamente al guardar'}
          </div>
        </Field>

        <Field label="Unidad de venta" required>
          <Select value={form.unidad_venta} onChange={e => setField('unidad_venta', e.target.value)}>
            <option value="m2">Metro cuadrado (m²)</option>
            <option value="pieza">Pieza</option>
            <option value="juego">Juego</option>
            <option value="caja">Caja</option>
            <option value="ml">Metro lineal</option>
          </Select>
        </Field>
      </div>

      <Field label="Nombre del producto" required error={errores.nombre}>
        <Input
          value={form.nombre}
          onChange={e => setField('nombre', e.target.value)}
          placeholder="Ej: Porcelanato Roma"
          error={errores.nombre}
        />
      </Field>

      <Field label="Descripción" hint="Visible en el showroom y catálogo">
        <Textarea
          value={form.descripcion}
          onChange={e => setField('descripcion', e.target.value)}
          placeholder="Características, uso recomendado, observaciones..."
        />
      </Field>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
        <Field label="Categoría" required error={errores.categoria_id}>
          <Select
            value={form.categoria_id}
            onChange={e => setField('categoria_id', e.target.value)}
            error={errores.categoria_id}
          >
            <option value="">Seleccionar categoría...</option>
            {(categorias || []).map(c => (
              <option key={c.id} value={c.id}>{c.nombre}</option>
            ))}
          </Select>
        </Field>

        <Field label="Marca">
          <Select value={form.marca_id} onChange={e => setField('marca_id', e.target.value)}>
            <option value="">Sin marca</option>
            {(marcas || []).map(m => (
              <option key={m.id} value={m.id}>{m.nombre}</option>
            ))}
          </Select>
        </Field>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
        <Field label="Precio de venta (Gs.)" required error={errores.precio_base}>
          <Input
            type="number" min="0" step="100"
            value={form.precio_base}
            onChange={e => setField('precio_base', e.target.value)}
            placeholder="0"
            error={errores.precio_base}
          />
        </Field>

        <Field label="Precio de costo (Gs.)" hint="Solo visible para administradores">
          <Input
            type="number" min="0" step="100"
            value={form.precio_costo}
            onChange={e => setField('precio_costo', e.target.value)}
            placeholder="0 (opcional)"
          />
        </Field>
      </div>

      {/* Tipos de instalación */}
      {tiposInst && tiposInst.length > 0 && (
        <Field label="Tipos de instalación">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {tiposInst.map(t => {
              const sel = form.tipos_instalacion_ids.includes(t.id)
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => toggleTipoInstalacion(t.id)}
                  style={{
                    padding: '5px 12px', borderRadius: '20px', cursor: 'pointer',
                    fontSize: '12px', fontWeight: '500', transition: 'all 120ms',
                    background: sel ? C.sidebar : 'transparent',
                    border: `1px solid ${sel ? C.gold : C.border}`,
                    color: sel ? C.gold : C.textSec,
                  }}
                >
                  {t.nombre}
                </button>
              )
            })}
          </div>
        </Field>
      )}

      {/* Opciones showroom */}
      <div style={{
        background: C.bgSec, border: `1px solid ${C.border}`,
        borderRadius: '10px', padding: '14px 16px',
        display: 'flex', flexDirection: 'column', gap: '10px',
      }}>
        <p style={{ fontSize: '11px', fontWeight: '500', color: C.textMuted,
          textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '2px' }}>
          Opciones de showroom
        </p>
        <Toggle
          value={form.destacado}
          onChange={v => setField('destacado', v)}
          label="Producto destacado (aparece primero en el showroom)"
        />
        <Toggle
          value={form.visible_showroom}
          onChange={v => setField('visible_showroom', v)}
          label="Visible en el showroom de tablets"
        />
      </div>

      <Field label="Notas internas" hint="Solo visible para el personal, no aparece en el showroom">
        <Textarea
          value={form.notas_internas}
          onChange={e => setField('notas_internas', e.target.value)}
          placeholder="Proveedor, condiciones especiales, alertas internas..."
        />
      </Field>
    </div>
  )
}

// ─── Paso 1: Variantes ────────────────────────────────────────────────────────

function FilaVariante({ variante, idx, errores, onChange, onEliminar, onAgregarImagen, onEliminarImagen }) {
  const { data: acabados } = useQuery({
    queryKey: ['acabados'],
    queryFn: () => productosApi.acabados().then(r => r.data?.results || r.data || []),
  })
  const fileRef = useRef()

  const dimError = errores[`variante_${idx}_dim`]

  return (
    <div style={{
      background: C.bg, border: `1px solid ${C.border}`,
      borderRadius: '12px', padding: '16px', marginBottom: '12px',
    }}>
      {/* Header de la variante */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{
            width: '24px', height: '24px', borderRadius: '50%',
            background: C.sidebar, border: `1px solid ${C.gold}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '11px', fontWeight: '600', color: C.gold, flexShrink: 0,
          }}>
            {idx + 1}
          </div>
          <span style={{ fontSize: '13px', fontWeight: '500', color: C.text }}>
            Variante {idx + 1}
            {variante.color && ` — ${variante.color}`}
            {variante.largo_cm && variante.ancho_cm && ` ${variante.largo_cm}×${variante.ancho_cm} cm`}
          </span>
        </div>
        <button
          type="button" onClick={onEliminar}
          style={{
            background: 'transparent', border: 'none', cursor: 'pointer',
            color: C.textMuted, padding: '4px', borderRadius: '6px',
            display: 'flex', alignItems: 'center', transition: 'color 120ms',
          }}
          onMouseEnter={e => e.currentTarget.style.color = C.danger}
          onMouseLeave={e => e.currentTarget.style.color = C.textMuted}
          title="Eliminar variante"
        >
          <Trash2 size={15} />
        </button>
      </div>

      {/* Atributos */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 14px' }}>
        <Field label="Color">
          <Input
            value={variante.color}
            onChange={e => onChange('color', e.target.value)}
            placeholder="Ej: Beige, Gris Cemento"
          />
        </Field>

        <Field label="Acabado">
          <Select
            value={variante.acabado_id || ''}
            onChange={e => onChange('acabado_id', e.target.value || null)}
          >
            <option value="">Sin acabado</option>
            {(acabados || []).map(a => (
              <option key={a.id} value={a.id}>{a.nombre}</option>
            ))}
          </Select>
        </Field>
      </div>

      {/* Dimensiones */}
      <p style={{ fontSize: '11px', fontWeight: '500', color: C.textMuted,
        textTransform: 'uppercase', letterSpacing: '0.06em', margin: '4px 0 10px' }}>
        Dimensiones
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0 10px' }}>
        <Field label="Largo (cm)" error={dimError}>
          <Input type="number" min="0" step="0.01"
            value={variante.largo_cm}
            onChange={e => onChange('largo_cm', e.target.value)}
            placeholder="Ej: 60"
            error={dimError}
          />
        </Field>
        <Field label="Ancho (cm)" error={dimError ? ' ' : undefined}>
          <Input type="number" min="0" step="0.01"
            value={variante.ancho_cm}
            onChange={e => onChange('ancho_cm', e.target.value)}
            placeholder="Ej: 60"
            error={dimError}
          />
        </Field>
        <Field label="Espesor (mm)">
          <Input type="number" min="0" step="0.1"
            value={variante.espesor_mm}
            onChange={e => onChange('espesor_mm', e.target.value)}
            placeholder="Ej: 8"
          />
        </Field>
      </div>

      {/* Rendimiento */}
      <p style={{ fontSize: '11px', fontWeight: '500', color: C.textMuted,
        textTransform: 'uppercase', letterSpacing: '0.06em', margin: '4px 0 10px' }}>
        Rendimiento por caja
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0 10px' }}>
        <Field label="Piezas/caja">
          <Input type="number" min="1" step="1"
            value={variante.piezas_por_caja}
            onChange={e => onChange('piezas_por_caja', e.target.value)}
            placeholder="Ej: 4"
          />
        </Field>
        <Field label="m²/caja" hint="Se calcula si no se completa">
          <Input type="number" min="0" step="0.0001"
            value={variante.m2_por_caja}
            onChange={e => onChange('m2_por_caja', e.target.value)}
            placeholder="Auto"
          />
        </Field>
        <Field label="Peso caja (kg)">
          <Input type="number" min="0" step="0.01"
            value={variante.peso_kg_caja}
            onChange={e => onChange('peso_kg_caja', e.target.value)}
            placeholder="Ej: 20.5"
          />
        </Field>
      </div>

      {/* Precio y stock */}
      <p style={{ fontSize: '11px', fontWeight: '500', color: C.textMuted,
        textTransform: 'uppercase', letterSpacing: '0.06em', margin: '4px 0 10px' }}>
        Precio y stock inicial
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '0 10px' }}>
        <Field label="Precio propio (Gs.)" hint="Vacío = usa precio base">
          <Input type="number" min="0" step="100"
            value={variante.precio_diferencial}
            onChange={e => onChange('precio_diferencial', e.target.value)}
            placeholder="Heredado"
          />
        </Field>
        <Field label="Stock inicial">
          <Input type="number" min="0" step="0.01"
            value={variante.stock_inicial}
            onChange={e => onChange('stock_inicial', e.target.value)}
            placeholder="0"
          />
        </Field>
        <Field label="Stock mínimo">
          <Input type="number" min="0" step="0.01"
            value={variante.stock_minimo}
            onChange={e => onChange('stock_minimo', e.target.value)}
            placeholder="0"
          />
        </Field>
        <Field label="Ubicación depósito">
          <Input
            value={variante.ubicacion}
            onChange={e => onChange('ubicacion', e.target.value)}
            placeholder="Ej: Pasillo A"
          />
        </Field>
      </div>

      {/* Imágenes de la variante */}
      <p style={{ fontSize: '11px', fontWeight: '500', color: C.textMuted,
        textTransform: 'uppercase', letterSpacing: '0.06em', margin: '4px 0 10px' }}>
        Imágenes de esta variante
      </p>
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'flex-start' }}>
        {variante._imagenes.map((img, i) => (
          <div key={i} style={{ position: 'relative' }}>
            <img
              src={img.preview} alt={`v${idx}-${i}`}
              style={{ width: '72px', height: '72px', objectFit: 'cover',
                borderRadius: '8px', border: `2px solid ${img.es_principal ? C.gold : C.border}`,
              }}
            />
            <button
              type="button" onClick={() => onEliminarImagen(i)}
              style={{
                position: 'absolute', top: '-6px', right: '-6px',
                width: '18px', height: '18px', borderRadius: '50%',
                background: C.danger, border: 'none', cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: '#fff', padding: 0,
              }}
            >
              <X size={10} />
            </button>
            {img.es_principal && (
              <div style={{
                position: 'absolute', bottom: '2px', left: '2px',
                background: C.sidebar, borderRadius: '4px',
                padding: '1px 4px', fontSize: '9px', color: C.gold,
              }}>
                ★
              </div>
            )}
          </div>
        ))}
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          style={{
            width: '72px', height: '72px', borderRadius: '8px',
            border: `1.5px dashed ${C.border}`, background: C.bgSec,
            cursor: 'pointer', display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', gap: '4px',
            color: C.textMuted, transition: 'all 120ms',
            flexShrink: 0,
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = C.gold; e.currentTarget.style.color = C.goldDark }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = C.border; e.currentTarget.style.color = C.textMuted }}
        >
          <Upload size={14} />
          <span style={{ fontSize: '10px' }}>Subir</span>
        </button>
        <input
          ref={fileRef} type="file" multiple accept="image/*"
          style={{ display: 'none' }}
          onChange={e => { onAgregarImagen(e.target.files); e.target.value = '' }}
        />
      </div>
    </div>
  )
}

function PasoVariantes({ variantes, errores, agregarVariante, eliminarVariante, setVarianteField, agregarImagenVariante, eliminarImagenVariante }) {
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
        <div>
          <p style={{ fontSize: '13px', color: C.textSec }}>
            Cada variante representa una combinación única de color, dimensión y acabado.
          </p>
        </div>
        <button
          type="button" onClick={agregarVariante}
          style={{
            display: 'flex', alignItems: 'center', gap: '6px',
            padding: '7px 14px', background: C.sidebar,
            border: `1px solid ${C.gold}`, borderRadius: '8px',
            color: C.gold, fontSize: '13px', cursor: 'pointer',
            whiteSpace: 'nowrap', transition: 'background 120ms', flexShrink: 0,
          }}
          onMouseEnter={e => e.currentTarget.style.background = C.sidebarHover}
          onMouseLeave={e => e.currentTarget.style.background = C.sidebar}
        >
          <Plus size={14} /> Agregar variante
        </button>
      </div>

      {variantes.map((v, idx) => (
        <FilaVariante
          key={idx}
          idx={idx}
          variante={v}
          errores={errores}
          onChange={(campo, valor) => setVarianteField(idx, campo, valor)}
          onEliminar={() => eliminarVariante(idx)}
          onAgregarImagen={(files) => agregarImagenVariante(idx, files)}
          onEliminarImagen={(idxI) => eliminarImagenVariante(idx, idxI)}
        />
      ))}

      {variantes.length === 0 && (
        <div style={{
          textAlign: 'center', padding: '40px 20px',
          border: `1.5px dashed ${C.border}`, borderRadius: '12px',
          color: C.textMuted,
        }}>
          <Package size={32} style={{ margin: '0 auto 10px', opacity: 0.3 }} />
          <p style={{ fontSize: '14px' }}>Sin variantes</p>
          <p style={{ fontSize: '12px', marginTop: '4px' }}>
            Hacé clic en "Agregar variante" para comenzar
          </p>
        </div>
      )}
    </div>
  )
}

// ─── Paso 2: Imágenes del producto ────────────────────────────────────────────

function PasoImagenes({ imagenes, agregarImagenes, eliminarImagen, marcarImagenPrincipal }) {
  const dropRef = useRef()
  const fileRef = useRef()

  const handleDrop = (e) => {
    e.preventDefault()
    const files = e.dataTransfer.files
    if (files.length) agregarImagenes(files)
    dropRef.current.style.borderColor = C.border
    dropRef.current.style.background  = C.bgSec
  }

  return (
    <div>
      {/* Zona de drop */}
      <div
        ref={dropRef}
        onClick={() => fileRef.current?.click()}
        onDragOver={e => {
          e.preventDefault()
          dropRef.current.style.borderColor = C.gold
          dropRef.current.style.background  = C.goldMuted
        }}
        onDragLeave={() => {
          dropRef.current.style.borderColor = C.border
          dropRef.current.style.background  = C.bgSec
        }}
        onDrop={handleDrop}
        style={{
          border: `2px dashed ${C.border}`, borderRadius: '12px',
          background: C.bgSec, padding: '32px 20px',
          textAlign: 'center', cursor: 'pointer',
          transition: 'all 150ms', marginBottom: '20px',
        }}
      >
        <Upload size={28} style={{ color: C.textMuted, margin: '0 auto 10px', display: 'block' }} />
        <p style={{ fontSize: '14px', fontWeight: '500', color: C.text, marginBottom: '4px' }}>
          Arrastrá imágenes aquí o hacé clic para seleccionar
        </p>
        <p style={{ fontSize: '12px', color: C.textMuted }}>
          JPG, PNG, WEBP — máximo 5 MB por imagen — recomendado 1200×1200 px
        </p>
        <input
          ref={fileRef} type="file" multiple accept="image/*"
          style={{ display: 'none' }}
          onChange={e => { agregarImagenes(e.target.files); e.target.value = '' }}
        />
      </div>

      {/* Galería de imágenes cargadas */}
      {imagenes.length > 0 ? (
        <>
          <p style={{ fontSize: '12px', color: C.textMuted, marginBottom: '12px' }}>
            {imagenes.length} imagen{imagenes.length !== 1 ? 'es' : ''} — hacé clic en ★ para marcar como principal
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: '12px' }}>
            {imagenes.map((img, i) => (
              <div key={i} style={{
                position: 'relative', borderRadius: '10px', overflow: 'hidden',
                border: `2px solid ${img.es_principal ? C.gold : C.border}`,
                background: C.bgSec,
              }}>
                <img
                  src={img.preview} alt={`img-${i}`}
                  style={{ width: '100%', aspectRatio: '1', objectFit: 'cover', display: 'block' }}
                />
                {/* Overlay de acciones */}
                <div style={{
                  position: 'absolute', inset: 0,
                  background: 'rgba(0,0,0,0)',
                  display: 'flex', alignItems: 'flex-start', justifyContent: 'flex-end',
                  padding: '6px', gap: '4px',
                  transition: 'background 120ms',
                }}
                onMouseEnter={e => e.currentTarget.style.background = 'rgba(0,0,0,0.25)'}
                onMouseLeave={e => e.currentTarget.style.background = 'rgba(0,0,0,0)'}
                >
                  <button
                    type="button" onClick={() => marcarImagenPrincipal(i)}
                    title="Marcar como imagen principal"
                    style={{
                      background: img.es_principal ? C.gold : 'rgba(0,0,0,0.5)',
                      border: 'none', borderRadius: '6px', padding: '5px',
                      cursor: 'pointer', color: img.es_principal ? C.sidebar : '#fff',
                      display: 'flex', alignItems: 'center',
                    }}
                  >
                    <Star size={13} fill={img.es_principal ? C.sidebar : 'none'} />
                  </button>
                  <button
                    type="button" onClick={() => eliminarImagen(i)}
                    title="Eliminar imagen"
                    style={{
                      background: 'rgba(154,48,48,0.85)', border: 'none',
                      borderRadius: '6px', padding: '5px', cursor: 'pointer',
                      color: '#fff', display: 'flex', alignItems: 'center',
                    }}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
                {img.es_principal && (
                  <div style={{
                    position: 'absolute', bottom: 0, left: 0, right: 0,
                    background: C.sidebar, padding: '3px 6px',
                    fontSize: '10px', color: C.gold, textAlign: 'center',
                    fontWeight: '500',
                  }}>
                    Imagen principal
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      ) : (
        <div style={{ textAlign: 'center', color: C.textMuted, padding: '20px' }}>
          <Image size={32} style={{ margin: '0 auto 8px', opacity: 0.25 }} />
          <p style={{ fontSize: '13px' }}>Sin imágenes aún</p>
        </div>
      )}
    </div>
  )
}

// ─── Barra de pasos ───────────────────────────────────────────────────────────

function BarraPasos({ paso, setPaso, errores }) {
  const pasos = [
    { label: 'Datos generales', desc: 'Código, nombre, precio' },
    { label: 'Variantes',       desc: 'Colores, dimensiones, stock' },
    { label: 'Imágenes',        desc: 'Fotos del producto' },
  ]
  const tieneErrorPaso0 = ['nombre','categoria_id','precio_base'].some(k => errores[k])

  return (
    <div style={{
      display: 'flex', borderBottom: `1px solid ${C.border}`,
      marginBottom: '24px',
    }}>
      {pasos.map((p, i) => {
        const activo = paso === i
        const hecho  = paso > i && !(i === 0 && tieneErrorPaso0)
        return (
          <button
            key={i}
            type="button"
            onClick={() => setPaso(i)}
            style={{
              flex: 1, padding: '12px 8px', background: 'transparent',
              border: 'none', borderBottom: `2px solid ${activo ? C.gold : 'transparent'}`,
              cursor: 'pointer', textAlign: 'left', transition: 'border-color 150ms',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '2px' }}>
              <div style={{
                width: '20px', height: '20px', borderRadius: '50%', flexShrink: 0,
                background: hecho ? C.success : (activo ? C.sidebar : C.bgSec),
                border: `1px solid ${hecho ? C.success : (activo ? C.gold : C.border)}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '10px', fontWeight: '600',
                color: hecho ? '#fff' : (activo ? C.gold : C.textMuted),
              }}>
                {hecho ? <CheckCircle size={12} color="#fff" /> : i + 1}
              </div>
              <span style={{ fontSize: '13px', fontWeight: activo ? '500' : '400', color: activo ? C.text : C.textSec }}>
                {p.label}
              </span>
            </div>
            <p style={{ fontSize: '11px', color: C.textMuted, paddingLeft: '26px' }}>{p.desc}</p>
          </button>
        )
      })}
    </div>
  )
}

// ─── Componente principal exportado ──────────────────────────────────────────

export default function ProductoForm({
  hook,           // resultado de useProductoForm()
  onCancelar,
  productoEdicion = null,
}) {
  const {
    form, variantes, imagenes, errores, paso, isLoading,
    setField, setPaso, guardar,
    agregarVariante, eliminarVariante, setVarianteField,
    agregarImagenVariante, eliminarImagenVariante,
    agregarImagenes, eliminarImagen, marcarImagenPrincipal,
  } = hook

  const esEdicion = Boolean(productoEdicion)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '18px 24px', borderBottom: `1px solid ${C.border}`, flexShrink: 0,
      }}>
        <div>
          <h2 style={{ fontSize: '16px', fontWeight: '500', color: C.text }}>
            {esEdicion ? 'Editar producto' : 'Nuevo producto'}
          </h2>
          {productoEdicion && (
            <p style={{ fontSize: '12px', color: C.textMuted, marginTop: '2px' }}>
              [{productoEdicion.codigo}] {productoEdicion.nombre}
            </p>
          )}
        </div>
        <button
          type="button" onClick={onCancelar}
          style={{
            background: 'transparent', border: 'none', cursor: 'pointer',
            color: C.textMuted, padding: '6px', borderRadius: '8px',
            display: 'flex', alignItems: 'center', transition: 'color 120ms',
          }}
          onMouseEnter={e => e.currentTarget.style.color = C.text}
          onMouseLeave={e => e.currentTarget.style.color = C.textMuted}
        >
          <X size={20} />
        </button>
      </div>

      {/* Barra de pasos */}
      <div style={{ padding: '0 24px', flexShrink: 0 }}>
        <BarraPasos paso={paso} setPaso={setPaso} errores={errores} />
      </div>

      {/* Contenido del paso */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 24px 24px' }}>
        {paso === 0 && <PasoDatos form={form} errores={errores} setField={setField} />}
        {paso === 1 && (
          <PasoVariantes
            variantes={variantes} errores={errores}
            agregarVariante={agregarVariante}
            eliminarVariante={eliminarVariante}
            setVarianteField={setVarianteField}
            agregarImagenVariante={agregarImagenVariante}
            eliminarImagenVariante={eliminarImagenVariante}
          />
        )}
        {paso === 2 && (
          <PasoImagenes
            imagenes={imagenes}
            agregarImagenes={agregarImagenes}
            eliminarImagen={eliminarImagen}
            marcarImagenPrincipal={marcarImagenPrincipal}
          />
        )}
      </div>

      {/* Footer con navegación */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '14px 24px', borderTop: `1px solid ${C.border}`,
        flexShrink: 0, background: C.bgSec,
      }}>
        <button
          type="button"
          onClick={paso === 0 ? onCancelar : () => setPaso(paso - 1)}
          style={{
            display: 'flex', alignItems: 'center', gap: '6px',
            padding: '8px 16px', background: 'transparent',
            border: `1px solid ${C.border}`, borderRadius: '8px',
            color: C.textSec, fontSize: '13px', cursor: 'pointer',
            transition: 'all 120ms',
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = C.gold; e.currentTarget.style.color = C.goldDark }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = C.border; e.currentTarget.style.color = C.textSec }}
        >
          <ChevronLeft size={15} />
          {paso === 0 ? 'Cancelar' : 'Anterior'}
        </button>

        <div style={{ display: 'flex', gap: '8px' }}>
          {/* Indicador de pasos */}
          {[0,1,2].map(i => (
            <div key={i} style={{
              width: i === paso ? '20px' : '6px', height: '6px',
              borderRadius: '3px', transition: 'width 200ms',
              background: i === paso ? C.gold : C.border,
            }} />
          ))}
        </div>

        {paso < 2 ? (
          <button
            type="button"
            onClick={() => setPaso(paso + 1)}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '8px 18px', background: C.sidebar,
              border: `1px solid ${C.gold}`, borderRadius: '8px',
              color: C.gold, fontSize: '13px', cursor: 'pointer',
              transition: 'background 120ms',
            }}
            onMouseEnter={e => e.currentTarget.style.background = C.sidebarHover}
            onMouseLeave={e => e.currentTarget.style.background = C.sidebar}
          >
            Siguiente <ChevronRight size={15} />
          </button>
        ) : (
          <button
            type="button"
            onClick={() => guardar(productoEdicion)}
            disabled={isLoading}
            style={{
              display: 'flex', alignItems: 'center', gap: '7px',
              padding: '8px 20px', background: isLoading ? C.sidebarHover : C.sidebar,
              border: `1px solid ${C.gold}`, borderRadius: '8px',
              color: C.gold, fontSize: '13px', fontWeight: '500',
              cursor: isLoading ? 'not-allowed' : 'pointer',
              transition: 'background 120ms',
            }}
          >
            {isLoading
              ? <><Loader2 size={15} style={{ animation: 'spin 1s linear infinite' }} /> Guardando...</>
              : <><CheckCircle size={15} /> {esEdicion ? 'Guardar cambios' : 'Crear producto'}</>
            }
          </button>
        )}
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
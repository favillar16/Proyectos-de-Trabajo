/**
 * Emite una nota de crédito o de débito sobre una factura.
 *
 * Es **un solo modal para los dos** a propósito: el gesto es el mismo —elegir
 * un motivo y confirmar sobre una factura ya emitida— y tener dos ventanas
 * casi iguales era la forma segura de que un día divergieran. Lo que cambia
 * de verdad son tres cosas, y están todas en `CFG`:
 *
 *   · **Crédito** revierte por el total y puede **reponer stock**; el monto
 *     sale de la factura, no se escribe.
 *   · **Débito** suma un importe **nuevo** —un interés, un flete, un ajuste
 *     hacia arriba— que hay que escribir, con su IVA. Nunca toca stock.
 *
 * Los motivos los sirve el backend (`motivos-nota` / `motivos-debito`) y no
 * se copian acá: son tablas de la DNIT. La lista del débito es más corta
 * porque los motivos de devolución quedan afuera — devolver mercadería baja
 * lo que el cliente debe, no lo sube.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, CheckCircle } from 'lucide-react'
import toast from 'react-hot-toast'

import { facturacionApi } from '../../services/api'
import { C, campo, etiqueta, formatGs } from './estilos'

const CFG = {
  credito: {
    titulo: 'Nota de crédito',
    verbo: 'Revierte',
    explica: 'Anula o corrige una factura ya emitida. Se emite por el total; ' +
             'el monto sale de la factura.',
    motivos: () => facturacionApi.motivosNota().then(r => r.data),
    emitir: (id, datos) => facturacionApi.notaCredito(id, datos),
    clave: 'nota_credito',
  },
  debito: {
    titulo: 'Nota de débito',
    verbo: 'Suma',
    explica: 'Le suma un importe a lo que el cliente debe: interés por mora, ' +
             'recupero de flete, ajuste de precio hacia arriba.',
    motivos: () => facturacionApi.motivosDebito().then(r => r.data),
    emitir: (id, datos) => facturacionApi.notaDebito(id, datos),
    clave: 'nota_debito',
  },
}

export default function ModalNota({ documento, tipo, onCerrar }) {
  const cfg = CFG[tipo]
  const queryClient = useQueryClient()
  const [motivo, setMotivo] = useState('')
  const [monto, setMonto] = useState('')
  const [tasaIva, setTasaIva] = useState(10)
  const [reponer, setReponer] = useState(null)
  const [observacion, setObservacion] = useState('')

  const { data: motivos = [] } = useQuery({
    queryKey: ['fe-motivos', tipo],
    queryFn: cfg.motivos,
    staleTime: Infinity,   // tabla de la DNIT: no cambia entre sesiones
  })

  const elegido = motivos.find(m => String(m.codigo) === String(motivo))
  // El backend decide reponer según el motivo si no se le dice nada; la
  // pantalla muestra esa decisión para que no sea una sorpresa, y deja
  // forzarla (mercadería devuelta rota vuelve al sistema pero no al stock).
  const reponePorDefecto = Boolean(elegido?.devuelve_mercaderia)
  const repondra = reponer === null ? reponePorDefecto : reponer

  const emitir = useMutation({
    mutationFn: () => cfg.emitir(documento.id, tipo === 'credito'
      ? { motivo: Number(motivo), reponer_stock: reponer, observacion }
      : { motivo: Number(motivo), monto, tasa_iva: tasaIva }),
    onSuccess: (r) => {
      queryClient.invalidateQueries({ queryKey: ['fe-documentos'] })
      toast.success(`${cfg.titulo} ${r.data[cfg.clave]?.numero || ''} emitida`)
      onCerrar()
    },
    onError: (err) => toast.error(
      err.response?.data?.error || `No se pudo emitir la ${cfg.titulo.toLowerCase()}`),
  })

  const listo = motivo && (tipo === 'credito' || Number(monto) > 0)

  return (
    <>
      <div onClick={onCerrar} style={{ position:'fixed', inset:0, zIndex:300,
        background:'rgba(26,23,20,0.45)', backdropFilter:'blur(2px)' }} />
      <div style={{ position:'fixed', zIndex:301, top:'50%', left:'50%',
        transform:'translate(-50%,-50%)', width:'min(520px,94vw)',
        maxHeight:'90vh', overflowY:'auto',
        background:C.bg, borderRadius:'14px', border:`1px solid ${C.border}`,
        boxShadow:'0 20px 60px rgba(0,0,0,0.22)', padding:'22px' }}>

        <h2 style={{ fontSize:'17px', fontWeight:'600', color:C.text,
          marginBottom:'4px' }}>
          {cfg.titulo}
        </h2>
        <p style={{ fontSize:'13px', color:C.textSec, marginBottom:'6px' }}>
          Sobre {documento.numero} · {documento.receptor_razon_social || 'Consumidor final'} ·{' '}
          {formatGs(documento.total)}
        </p>
        <p style={{ fontSize:'12px', color:C.textMuted, marginBottom:'16px' }}>
          {cfg.explica}
        </p>

        <label style={etiqueta}>Motivo *</label>
        <select value={motivo} onChange={e => { setMotivo(e.target.value); setReponer(null) }}
          style={{ ...campo, cursor:'pointer', marginBottom:'12px' }}>
          <option value="">Elegí un motivo…</option>
          {motivos.map(m => (
            <option key={m.codigo} value={m.codigo}>{m.descripcion}</option>
          ))}
        </select>

        {tipo === 'debito' && (
          <div style={{ display:'grid', gap:'10px', marginBottom:'12px',
            gridTemplateColumns:'2fr 1fr' }}>
            <div>
              <label style={etiqueta}>Monto con IVA incluido (Gs) *</label>
              <input value={monto} onChange={e => setMonto(e.target.value)}
                style={campo} inputMode="numeric" placeholder="150000" />
            </div>
            <div>
              <label style={etiqueta}>IVA</label>
              <select value={tasaIva} onChange={e => setTasaIva(Number(e.target.value))}
                style={{ ...campo, cursor:'pointer' }}>
                <option value={10}>10%</option>
                <option value={5}>5%</option>
                <option value={0}>Exento</option>
              </select>
            </div>
          </div>
        )}

        {tipo === 'credito' && motivo && (
          <>
            <div style={{ padding:'10px 12px', borderRadius:'9px',
              marginBottom:'12px',
              background: repondra ? C.successBg : C.bgTer,
              border:`1px solid ${repondra ? C.success : C.border}44` }}>
              <label style={{ display:'flex', alignItems:'center', gap:'9px',
                cursor:'pointer', fontSize:'12.5px',
                color: repondra ? C.success : C.textSec }}>
                <input type="checkbox" checked={repondra}
                  onChange={e => setReponer(e.target.checked)} />
                Devolver la mercadería al stock
              </label>
              <p style={{ fontSize:'11px', color:C.textMuted, margin:'6px 0 0' }}>
                {reponePorDefecto
                  ? 'Este motivo devuelve mercadería, así que viene marcado. Destildalo si volvió rota.'
                  : 'Este motivo no devuelve mercadería (un descuento no reingresa nada al depósito).'}
              </p>
            </div>
            <label style={etiqueta}>Observación (opcional)</label>
            <input value={observacion} onChange={e => setObservacion(e.target.value)}
              style={{ ...campo, marginBottom:'4px' }}
              placeholder="Queda en el movimiento de stock" />
          </>
        )}

        <div style={{ display:'flex', gap:'8px', marginTop:'18px' }}>
          <button onClick={onCerrar}
            style={{ flex:1, height:'42px', borderRadius:'9px', cursor:'pointer',
              background:'transparent', border:`1px solid ${C.border}`,
              color:C.textSec, fontSize:'13.5px', fontFamily:'inherit' }}>
            Volver
          </button>
          <button disabled={!listo || emitir.isPending}
            onClick={() => emitir.mutate()}
            style={{ flex:1, height:'42px', borderRadius:'9px',
              cursor: listo ? 'pointer' : 'not-allowed', opacity: listo ? 1 : 0.55,
              display:'flex', alignItems:'center', justifyContent:'center', gap:'7px',
              background:C.sidebar, border:`1px solid ${C.gold}`, color:C.gold,
              fontSize:'13.5px', fontFamily:'inherit' }}>
            {emitir.isPending
              ? <Loader2 size={15} style={{ animation:'spin 1s linear infinite' }}/>
              : <CheckCircle size={15}/>}
            Emitir
          </button>
        </div>
      </div>
    </>
  )
}

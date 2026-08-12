/**
 * useProductoForm
 * Hook que centraliza el estado y la lógica del formulario de producto.
 * Separa la lógica del componente visual para mantener el JSX limpio.
 */
import { useState, useCallback } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { productosApi } from '../services/api'
import toast from 'react-hot-toast'

const VARIANTE_VACÍA = {
  id:              null,     // presente solo si la variante ya existe en el backend (edición)
  color:           '',
  acabado_id:      null,
  largo_cm:        '',
  ancho_cm:        '',
  piezas_por_caja: '',
  m2_por_caja:     '',
  cajas_por_pallet: '',
  precio_diferencial: '',
  tipo_grifo:      '',
  posicion_grifo:  '',
  montaje_grifo:   '',
  tipo_ducha:      '',
  tipo_cisterna:   '',
  stock_inicial:   '',
  stock_inicial_unidad: 'venta',   // venta | caja | pallet — unidad en la que se cargó stock_inicial
  stock_minimo:    '',
  ubicacion:       '',
  activa:          true,
  _imagenes:       [],      // archivos File[] locales antes de subir, o imágenes ya existentes (_existente: true)
}

const PRODUCTO_VACÍO = {
  codigo:              '',
  nombre:              '',
  categoria_id:        '',
  marca_id:            '',
  precio_base:         '',
  precio_costo:        '',
  unidad_venta:        'm2',
  destacado:           false,
  visible_showroom:    true,
  notas_internas:      '',
}

export function useProductoForm({ onSuccess } = {}) {
  const queryClient = useQueryClient()

  // ── Estado del formulario ────────────────────────────────
  const [form,      setForm]      = useState(PRODUCTO_VACÍO)
  const [variantes, setVariantes] = useState([{ ...VARIANTE_VACÍA }])
  const [imagenes,  setImagenes]  = useState([])      // { file, preview, es_principal }[]
  const [errores,   setErrores]   = useState({})
  const [paso,      setPaso]      = useState(0)       // 0=datos, 1=variantes, 2=imágenes

  // ── Actualizar campo del producto ────────────────────────
  const setField = useCallback((campo, valor) => {
    setForm(prev => ({ ...prev, [campo]: valor }))
    setErrores(prev => { const e = { ...prev }; delete e[campo]; return e })
  }, [])

  // ── Variantes ────────────────────────────────────────────
  const agregarVariante = useCallback(() => {
    setVariantes(prev => [...prev, { ...VARIANTE_VACÍA }])
  }, [])

  const eliminarVariante = useCallback((idx) => {
    setVariantes(prev => prev.filter((_, i) => i !== idx))
  }, [])

  const setVarianteField = useCallback((idx, campo, valor) => {
    setVariantes(prev => prev.map((v, i) =>
      i === idx ? { ...v, [campo]: valor } : v
    ))
  }, [])

  const agregarImagenVariante = useCallback((idx, files) => {
    setVariantes(prev => prev.map((v, i) => {
      if (i !== idx) return v
      const nuevas = Array.from(files).map(f => ({
        file: f,
        preview: URL.createObjectURL(f),
        es_principal: v._imagenes.length === 0,
      }))
      return { ...v, _imagenes: [...v._imagenes, ...nuevas] }
    }))
  }, [])

  const eliminarImagenVariante = useCallback((idxV, idxI) => {
    setVariantes(prev => prev.map((v, i) => {
      if (i !== idxV) return v
      const imgAEliminar = v._imagenes[idxI]
      // Si ya estaba subida al servidor, borrarla también ahí (si no, solo
      // desaparecería de esta pantalla y volvería a aparecer al reabrir).
      if (imgAEliminar?._existente && v.id) {
        productosApi.eliminarImagenVariante(v.id, imgAEliminar.id)
          .catch(() => toast.error('No se pudo eliminar la imagen'))
      }
      const imgs = v._imagenes.filter((_, j) => j !== idxI)
      // Si se eliminó la principal, marcar la primera como principal
      if (imgs.length > 0 && !imgs.some(img => img.es_principal)) {
        imgs[0].es_principal = true
      }
      return { ...v, _imagenes: imgs }
    }))
  }, [])

  // ── Imágenes del producto ────────────────────────────────
  const agregarImagenes = useCallback((files) => {
    const nuevas = Array.from(files).map((file, i) => ({
      file,
      preview: URL.createObjectURL(file),
      es_principal: imagenes.length === 0 && i === 0,
    }))
    setImagenes(prev => [...prev, ...nuevas])
  }, [imagenes.length])

  const eliminarImagen = useCallback((idx) => {
    setImagenes(prev => {
      const arr = prev.filter((_, i) => i !== idx)
      if (arr.length > 0 && !arr.some(img => img.es_principal)) {
        arr[0].es_principal = true
      }
      return arr
    })
  }, [])

  const marcarImagenPrincipal = useCallback((idx) => {
    setImagenes(prev => prev.map((img, i) => ({ ...img, es_principal: i === idx })))
  }, [])

  // ── Validación ───────────────────────────────────────────
  const validar = useCallback(() => {
    const e = {}
    // El código se genera automáticamente en el backend; no se valida aquí.
    if (!form.nombre.trim())       e.nombre      = 'El nombre es obligatorio'
    if (!form.categoria_id)        e.categoria_id = 'Seleccioná una categoría'
    if (!form.precio_base || Number(form.precio_base) <= 0)
                                   e.precio_base = 'El precio debe ser mayor a 0'

    variantes.forEach((v, i) => {
      if (Boolean(v.largo_cm) !== Boolean(v.ancho_cm)) {
        e[`variante_${i}_dim`] = 'Completar largo y ancho juntos'
      }
    })

    setErrores(e)
    return Object.keys(e).length === 0
  }, [form, variantes])

  // ── Mutación principal ───────────────────────────────────
  const mutation = useMutation({
    mutationFn: async (productoExistente) => {
      const esEdicion = Boolean(productoExistente?.id)

      // 1. Crear o actualizar el producto
      // El código se genera automáticamente en el backend; no se envía.
      const { codigo: _codigoIgnorado, ...formSinCodigo } = form
      const payload = {
        ...formSinCodigo,
        // Campos opcionales: enviar null (no cadena vacía) para que el backend
        // no los rechace. Un DecimalField/FK no acepta "".
        marca_id:     form.marca_id || null,
        precio_costo: form.precio_costo === '' || form.precio_costo == null ? null : form.precio_costo,
        // precio_base es obligatorio: si viene vacío, mandar 0 para que el backend
        // dé un error claro de "mayor a 0" en vez de "número inválido".
        precio_base:  form.precio_base === '' || form.precio_base == null ? 0 : form.precio_base,
      }

      let productoId
      if (esEdicion) {
        const res = await productosApi.actualizar(productoExistente.id, payload)
        productoId = res.data.id
      } else {
        const res = await productosApi.crear(payload)
        productoId = res.data.id
      }

      // 2. Subir imágenes del producto
      for (let i = 0; i < imagenes.length; i++) {
        const img = imagenes[i]
        const fd  = new FormData()
        fd.append('imagen',       img.file)
        fd.append('es_principal', img.es_principal ? 'true' : 'false')
        fd.append('orden',        i)
        await productosApi.subirImagen(productoId, fd)
      }

      // 3. Crear o actualizar variantes y subir sus imágenes nuevas
      for (const variante of variantes) {
        const { id: varianteExistenteId, _imagenes, ...datosVariante } = variante
        const esVarianteExistente = Boolean(varianteExistenteId)

        // Limpiar campos vacíos opcionales
        const varPayload = Object.fromEntries(
          Object.entries(datosVariante).filter(([, v]) => v !== '' && v !== null)
        )
        // El stock (cantidad) de una variante ya creada se ajusta desde
        // Inventario (que sí pasa por el historial de movimientos) — acá
        // solo se editan sus datos y, como mucho, el mínimo/ubicación.
        if (esVarianteExistente) { delete varPayload.stock_inicial; delete varPayload.stock_inicial_unidad }

        let varianteId
        if (esVarianteExistente) {
          await productosApi.actualizarVariante(varianteExistenteId, varPayload)
          varianteId = varianteExistenteId
        } else {
          const resV = await productosApi.agregarVariante(productoId, varPayload)
          varianteId = resV.data.id
        }

        // Subir solo las imágenes nuevas de esta sesión (las ya existentes
        // se suben una sola vez, al crearlas; acá se identifican con `file`)
        const imagenesNuevas = _imagenes.filter(img => img.file)
        for (let i = 0; i < imagenesNuevas.length; i++) {
          const img = imagenesNuevas[i]
          const fd  = new FormData()
          fd.append('imagen',       img.file)
          fd.append('es_principal', img.es_principal ? 'true' : 'false')
          fd.append('orden',        i)
          await productosApi.subirImagenVariante(varianteId, fd)
        }
      }

      return productoId
    },

    onSuccess: (productoId) => {
      queryClient.invalidateQueries({ queryKey: ['productos'] })
      toast.success('Producto guardado correctamente')
      resetForm()
      onSuccess?.(productoId)
    },

    onError: (err) => {
      const data = err.response?.data
      if (data && typeof data === 'object') {
        // Traducir nombres técnicos a etiquetas legibles
        const ETIQUETAS = {
          nombre: 'Nombre', categoria_id: 'Categoría', categoria: 'Categoría',
          precio_base: 'Precio de venta', precio_costo: 'Precio de costo',
          marca_id: 'Marca', unidad_venta: 'Unidad de venta',
          codigo: 'Código',
          non_field_errors: 'Datos del producto',
        }
        // Marcar los campos con error en el formulario (se ven en rojo)
        const erroresCampos = {}
        Object.entries(data).forEach(([campo, msgs]) => {
          const texto = Array.isArray(msgs) ? msgs.join(' ') : String(msgs)
          erroresCampos[campo] = texto
        })
        setErrores(prev => ({ ...prev, ...erroresCampos }))
        // Volver al primer paso si el error es de datos generales
        if (Object.keys(data).some(k => ['nombre','categoria_id','categoria','precio_base','unidad_venta','codigo'].includes(k))) {
          setPaso(0)
        }
        // 'detail' es la clave genérica de DRF para errores de sesión/permiso
        // (401 token vencido, 403 sin permiso) — no es un campo del
        // formulario, mostrarlo tal cual en vez de "detail: ...".
        const detalle = (typeof data.detail === 'string' && Object.keys(data).length <= 2)
          ? data.detail
          : Object.entries(data)
              .map(([campo, msgs]) => `${ETIQUETAS[campo] || campo}: ${Array.isArray(msgs) ? msgs.join(' ') : msgs}`)
              .join(' · ')
        toast.error(detalle || 'Revisá los campos marcados')
      } else {
        toast.error('Error al guardar el producto')
      }
    },
  })

  // ── Cargar datos para edición ────────────────────────────
  const mapearVarianteExistente = (v) => ({
    id:                 v.id,
    color:              v.color || '',
    calidad:            v.calidad || '',
    acabado_id:         v.acabado?.id || null,
    largo_cm:           v.largo_cm ?? '',
    ancho_cm:           v.ancho_cm ?? '',
    piezas_por_caja:    v.piezas_por_caja ?? '',
    m2_por_caja:        v.m2_por_caja ?? '',
    cajas_por_pallet:   v.cajas_por_pallet ?? '',
    precio_diferencial: v.precio_diferencial ?? '',
    tipo_grifo:         v.tipo_grifo || '',
    posicion_grifo:     v.posicion_grifo || '',
    montaje_grifo:      v.montaje_grifo || '',
    tipo_ducha:         v.tipo_ducha || '',
    tipo_cisterna:      v.tipo_cisterna || '',
    stock_inicial:      v.stock?.cantidad ?? '',
    stock_inicial_unidad: 'venta',
    stock_minimo:       v.stock?.stock_minimo ?? '',
    ubicacion:          v.stock?.ubicacion ?? '',
    activa:             v.activa,
    _imagenes: (v.imagenes || []).map(img => ({
      id: img.id, preview: img.imagen_url, es_principal: img.es_principal, _existente: true,
    })),
  })

  const cargarParaEdicion = useCallback(async (producto) => {
    // El producto que llega desde el listado (grid de Productos) no trae
    // categoría/marca completas ni variantes — solo trae nombres planos
    // para la tarjeta. Se pide el detalle completo para no perder la
    // categoría/marca seleccionada, y para traer las variantes reales:
    // sin esto, guardar sin tocar el paso "Variantes" creaba una variante
    // vacía nueva cada vez (y una segunda edición chocaba con datos
    // duplicados y tiraba error al guardar).
    setPaso(0)
    setVariantes([{ ...VARIANTE_VACÍA }])
    setImagenes([])
    setForm({
      codigo:              producto.codigo,
      nombre:              producto.nombre,
      categoria_id:        producto.categoria?.id || '',
      marca_id:            producto.marca?.id || '',
      precio_base:         producto.precio_base,
      precio_costo:        producto.precio_costo || '',
      unidad_venta:        producto.unidad_venta,
      destacado:           producto.destacado,
      visible_showroom:    producto.visible_showroom,
      notas_internas:      producto.notas_internas || '',
    })

    try {
      const { data: detalle } = await productosApi.detalle(producto.id)
      setForm({
        codigo:              detalle.codigo,
        nombre:              detalle.nombre,
        categoria_id:        detalle.categoria?.id || '',
        marca_id:            detalle.marca?.id || '',
        precio_base:         detalle.precio_base,
        precio_costo:        detalle.precio_costo || '',
        unidad_venta:        detalle.unidad_venta,
        destacado:           detalle.destacado,
        visible_showroom:    detalle.visible_showroom,
        notas_internas:      detalle.notas_internas || '',
      })
      const variantesExistentes = (detalle.variantes || []).map(mapearVarianteExistente)
      setVariantes(variantesExistentes.length > 0 ? variantesExistentes : [{ ...VARIANTE_VACÍA }])
    } catch {
      toast.error('No se pudo cargar el detalle completo del producto')
    }
  }, [])

  const resetForm = useCallback(() => {
    setForm(PRODUCTO_VACÍO)
    setVariantes([{ ...VARIANTE_VACÍA }])
    setImagenes([])
    setErrores({})
    setPaso(0)
  }, [])

  const guardar = useCallback((productoExistente = null) => {
    if (!validar()) {
      if (paso > 0) setPaso(0)  // Volver al paso con errores
      return
    }
    mutation.mutate(productoExistente)
  }, [validar, mutation, paso])

  return {
    // Estado
    form, variantes, imagenes, errores, paso,
    isLoading: mutation.isPending,
    // Acciones producto
    setField, resetForm, cargarParaEdicion, guardar,
    // Navegación pasos
    setPaso,
    // Acciones variantes
    agregarVariante, eliminarVariante, setVarianteField,
    agregarImagenVariante, eliminarImagenVariante,
    // Acciones imágenes producto
    agregarImagenes, eliminarImagen, marcarImagenPrincipal,
  }
}
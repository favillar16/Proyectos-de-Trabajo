/**
 * Abrir e imprimir un PDF que vino del backend como blob.
 *
 * Hoy lo usa la planilla de etiquetas de código de barras, que sale por la
 * Epson L1250. Los comprobantes NO pasan por acá: el ticket sale solo por la
 * térmica, y la factura por su propio equipo.
 *
 * Por qué un blob y no una URL directa: los endpoints piden JWT en el header
 * Authorization, y una pestaña abierta con window.open() no lo manda. Pasar el
 * token por la query lo dejaría en el historial del navegador y en los logs
 * del servidor, así que el PDF se baja por axios (con el header puesto por el
 * interceptor) y recién ahí se lo muestra.
 *
 * La impresora se elige en el diálogo del navegador.
 */

/** Abre el PDF en una pestaña nueva y dispara el diálogo de impresión. */
export function abrirPdfParaImprimir(blobData, { imprimir = true } = {}) {
  const url = window.URL.createObjectURL(
    new Blob([blobData], { type: 'application/pdf' }))

  const ventana = window.open(url, '_blank')

  if (!ventana) {
    // Bloqueador de pop-ups. Se cae a la descarga, que nunca se bloquea, y
    // el que llama avisa qué pasó.
    descargarPdf(blobData, 'documento.pdf')
    window.URL.revokeObjectURL(url)
    return false
  }

  if (imprimir) {
    // El print() tiene que esperar a que el visor de PDF termine de cargar;
    // llamarlo antes abre un diálogo sobre una página en blanco.
    ventana.addEventListener('load', () => {
      try {
        ventana.focus()
        ventana.print()
      } catch {
        // Algunos visores embebidos no dejan llamar print() desde afuera.
        // No es un error: la pestaña ya está abierta con el PDF y la cajera
        // puede imprimir con Ctrl+P.
      }
    })
  }

  // El objectURL se libera cuando la pestaña se cierra. Revocarlo antes deja
  // la pestaña mostrando un PDF que ya no existe.
  ventana.addEventListener('unload', () => window.URL.revokeObjectURL(url))
  return true
}

/** Baja el PDF como archivo, sin abrirlo. */
export function descargarPdf(blobData, nombreArchivo) {
  const url = window.URL.createObjectURL(
    new Blob([blobData], { type: 'application/pdf' }))
  const a = document.createElement('a')
  a.href = url
  a.download = nombreArchivo
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

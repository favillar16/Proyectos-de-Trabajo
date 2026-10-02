/**
 * Manda un PDF a la impresora sin pasar por la carpeta de descargas.
 *
 * Los documentos (nota de pedido, KuDE de la remisión) solo se podían bajar:
 * para imprimir había que buscar el archivo y abrirlo. Acá el PDF se carga en
 * un iframe oculto y se abre el diálogo de impresión del navegador.
 *
 * En la tablet (Chrome de Android) un iframe no muestra PDFs, así que ahí se
 * abre en una pestaña nueva y se imprime desde el visor. Lo mismo si el
 * navegador bloquea el diálogo desde el iframe.
 */
const esMovil = () => /Android|iPhone|iPad/i.test(navigator.userAgent)

export function imprimirPdf(datos) {
  const blob = datos instanceof Blob ? datos : new Blob([datos], { type: 'application/pdf' })
  const pdf = blob.type === 'application/pdf' ? blob : new Blob([blob], { type: 'application/pdf' })
  const url = window.URL.createObjectURL(pdf)

  if (esMovil()) {
    window.open(url, '_blank')
    // La pestaña nueva necesita la URL viva un rato para cargarla.
    setTimeout(() => window.URL.revokeObjectURL(url), 60_000)
    return
  }

  const iframe = document.createElement('iframe')
  // Ni display:none ni tamaño cero: con eso el visor de PDF de Chrome no
  // llega a cargar y print() imprime una hoja en blanco.
  iframe.style.cssText = 'position:fixed;right:0;bottom:0;width:1px;height:1px;border:0;opacity:0'
  iframe.src = url
  iframe.onload = () => {
    try {
      iframe.contentWindow.focus()
      iframe.contentWindow.print()
    } catch {
      window.open(url, '_blank')
    }
  }
  document.body.appendChild(iframe)
  // El diálogo de impresión no avisa cuándo se cierra: se limpia después.
  setTimeout(() => {
    iframe.remove()
    window.URL.revokeObjectURL(url)
  }, 60_000)
}

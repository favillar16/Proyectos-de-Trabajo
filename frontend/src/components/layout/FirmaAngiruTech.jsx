/**
 * Firma del desarrollador — marca de agua de AngiruTech en el pie de página.
 *
 * Va apagada (gris y semitransparente) para no competir con la marca del
 * local, que es la protagonista de cada pantalla; recupera el color al pasar
 * el mouse. El logo es `logo-claro.png` del kit de marca de AngiruTech,
 * recortado a su contenido: está pensado para fondos claros, como el del
 * contenido y la tarjeta del login.
 */
import { useState } from 'react'
import logoAngiruTech from '../../assets/logo_angiru_tech.png'

export default function FirmaAngiruTech({ alto = 18 }) {
  const [hover, setHover] = useState(false)
  return (
    <span
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      title="Sistema desarrollado por AngiruTech"
      style={{
        display:    'inline-flex',
        alignItems: 'center',
        gap:        '7px',
        opacity:    hover ? 0.95 : 0.5,
        filter:     hover ? 'none' : 'grayscale(1)',
        transition: 'opacity 160ms ease, filter 160ms ease',
        userSelect: 'none',
      }}
    >
      <span style={{ fontSize: '10.5px', color: '#6b6560', letterSpacing: '0.04em' }}>
        Desarrollado por
      </span>
      <img
        src={logoAngiruTech}
        alt="AngiruTech"
        draggable={false}
        style={{ height: alto, width: 'auto', display: 'block' }}
      />
    </span>
  )
}

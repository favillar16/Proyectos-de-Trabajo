#!/usr/bin/env bash
#
# Genera un certificado .p12 AUTOFIRMADO para probar la firma localmente.
#
#     bash sidecar/herramientas/certificado_prueba.sh [carpeta-destino]
#
# ⚠️ ESTE CERTIFICADO NO SIRVE PARA FACTURAR. No lo emite un prestador
# habilitado, así que el SIFEN rechaza el handshake y cualquier documento
# firmado con él. Sirve para una sola cosa, y es bastante: verificar toda la
# mecánica de firma sin esperar al certificado de verdad —que el .p12 abra,
# que la clave sea la correcta, que se firme el nodo que corresponde, que la
# referencia apunte al CDC, que el QR se calcule con el CSC—. Lo único que no
# prueba es la autenticación mutua contra el SIFEN, que es justamente lo que
# necesita el certificado real.
#
# No es un atajo inventado: la Guía de Pruebas de e-Kuatia §2 pide, como uno
# de sus escenarios, intentar conectarse con un certificado "no válido" que el
# contribuyente se autogenera. Este es ese certificado.
#
# El .p12 que sale NO se versiona (.gitignore ya cubre *.p12 y *.pfx) y por
# defecto se escribe FUERA del repositorio, para que no haya forma de que
# termine en un commit por accidente.
set -euo pipefail

DESTINO="${1:-$(cd "$(dirname "$0")/../.." && pwd)/../certificados_prueba}"
CLAVE="${CLAVE_P12:-prueba123}"

mkdir -p "$DESTINO"
cd "$DESTINO"

cat > openssl.cnf <<'EOF'
[req]
distinguished_name = dn
x509_extensions = v3
prompt = no
[dn]
C  = PY
O  = CERTIFICADO DE PRUEBA - SIN VALOR LEGAL
CN = OGA PORA E.A.S. (PRUEBA)
serialNumber = RUC80173107-0
[v3]
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment, nonRepudiation
# clientAuth es la extensión que el SIFEN exige de verdad, porque hace
# autenticación mutua TLS. Se la ponemos para que el .p12 de prueba tenga la
# misma forma que el real y no oculte un problema de configuración.
extendedKeyUsage = clientAuth, emailProtection
subjectAltName = email:prueba@ejemplo.invalid
EOF

openssl req -x509 -newkey rsa:2048 -keyout clave.pem -out cert.pem \
  -days 400 -nodes -config openssl.cnf 2>/dev/null

openssl pkcs12 -export -out prueba.p12 -inkey clave.pem -in cert.pem \
  -passout "pass:${CLAVE}" -name "Oga Pora prueba" 2>/dev/null

echo "Certificado de PRUEBA generado (sin valor legal):"
echo "  archivo: $DESTINO/prueba.p12"
echo "  clave:   ${CLAVE}"
echo
openssl x509 -in cert.pem -noout -ext extendedKeyUsage
openssl x509 -in cert.pem -noout -enddate
echo
echo "Para usarlo, en backend/.env:"
echo "  SIFEN_CERT_PATH=$DESTINO/prueba.p12"
echo "  SIFEN_CERT_PASSWORD=${CLAVE}"
echo
echo "Despues reiniciar el sidecar y correr:"
echo "  python manage.py sifen_probar --documento <id> --firmar"

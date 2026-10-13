#!/usr/bin/env bash
# Instala Ordenito para tu usuario (no necesita sudo).
set -euo pipefail
cd "$(dirname "$0")"

BIN="$HOME/.local/bin/ordenito"
CONF="${XDG_CONFIG_HOME:-$HOME/.config}/ordenito/reglas.conf"
UNITS="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
DESCARGAS="$(xdg-user-dir DOWNLOAD 2>/dev/null || true)"
[[ -d "$DESCARGAS" && "$DESCARGAS" != "$HOME" ]] || DESCARGAS="$HOME/Downloads"

verde() { printf '\033[32m%s\033[0m\n' "$*"; }
aviso() { printf '\033[33m%s\033[0m\n' "$*"; }

python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' \
    || { echo "Ordenito necesita Python 3.9 o más nuevo."; exit 1; }
command -v pdftotext >/dev/null \
    || aviso "· Opcional: instala poppler-utils (pdftotext) para que lea el contenido de los PDF."

install -Dm755 ordenito.py "$BIN"
verde "✓ Programa:  $BIN"

if [[ -f "$CONF" ]]; then
    verde "✓ Reglas:    $CONF (ya existían, no se tocan)"
else
    install -Dm644 reglas.ejemplo.conf "$CONF"
    verde "✓ Reglas:    $CONF (ejemplo, edítalas a tu gusto)"
fi

mkdir -p "$UNITS"
sed "s|@DESCARGAS@|$DESCARGAS|" systemd/ordenito.path > "$UNITS/ordenito.path"
cp systemd/ordenito.service "$UNITS/ordenito.service"
systemctl --user daemon-reload
systemctl --user enable --now ordenito.path >/dev/null
verde "✓ Servicio:  vigilando $DESCARGAS"

[[ ":$PATH:" == *":$HOME/.local/bin:"* ]] || aviso "· Agrega ~/.local/bin a tu PATH para usar el comando 'ordenito'."

cat <<FIN

Listo. Todo lo que descargues se ordenará solo.
  ordenito simular            qué haría ahora mismo
  ordenito explicar ARCHIVO   por qué un archivo va a donde va
  ordenito deshacer           devuelve el último archivo movido
FIN

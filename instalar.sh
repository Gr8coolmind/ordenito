#!/usr/bin/env bash
# Instala Ordenito para tu usuario (no necesita sudo). Funciona en Linux (systemd) y macOS (launchd).
# ORDENITO_SIN_SERVICIO=1 instala sin activar el servicio (útil para pruebas).
set -euo pipefail
cd "$(dirname "$0")"

BIN="$HOME/.local/bin/ordenito"
CONF="${XDG_CONFIG_HOME:-$HOME/.config}/ordenito/reglas.conf"
ESTADO="${XDG_STATE_HOME:-$HOME/.local/state}/ordenito"
DESCARGAS="$(xdg-user-dir DOWNLOAD 2>/dev/null || true)"
[[ -d "$DESCARGAS" && "$DESCARGAS" != "$HOME" ]] || DESCARGAS="$HOME/Downloads"
SISTEMA="$(uname -s)"

verde() { printf '\033[32m%s\033[0m\n' "$*"; }
aviso() { printf '\033[33m%s\033[0m\n' "$*"; }

PYTHON="$(command -v python3 || true)"
if [[ -z "$PYTHON" ]] || ! "$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
    echo "Ordenito necesita Python 3.9 o más nuevo."
    [[ "$SISTEMA" == Darwin ]] && echo "En Mac: ejecuta 'xcode-select --install' o 'brew install python'."
    exit 1
fi
# En Mac /usr/bin/python3 es un intermediario: usamos el ejecutable real (al que se le dan los permisos)
PYTHON="$("$PYTHON" -c 'import os, sys; print(os.path.realpath(sys.executable))')"

if ! command -v pdftotext >/dev/null; then
    if [[ "$SISTEMA" == Darwin ]]; then
        aviso "· Opcional: 'brew install poppler' para que lea el contenido de los PDF."
    else
        aviso "· Opcional: instala poppler-utils (pdftotext) para que lea el contenido de los PDF."
    fi
fi

mkdir -p "$(dirname "$BIN")" "$(dirname "$CONF")" "$ESTADO"
install -m 755 ordenito.py "$BIN"
verde "✓ Programa:  $BIN"

if [[ -f "$CONF" ]]; then
    verde "✓ Reglas:    $CONF (ya existían, no se tocan)"
else
    if [[ "$SISTEMA" == Darwin ]]; then
        sed 's|^\[Videos\]$|[Movies]|' reglas.ejemplo.conf > "$CONF"   # en Mac la carpeta se llama Películas/Movies
    else
        cp reglas.ejemplo.conf "$CONF"
    fi
    verde "✓ Reglas:    $CONF (ejemplo, edítalas a tu gusto)"
fi

if [[ -n "${ORDENITO_SIN_SERVICIO:-}" ]]; then
    aviso "· Servicio no activado (ORDENITO_SIN_SERVICIO)."
elif [[ "$SISTEMA" == Darwin ]]; then
    PLIST="$HOME/Library/LaunchAgents/com.gr8coolmind.ordenito.plist"
    mkdir -p "$(dirname "$PLIST")"
    sed -e "s|@PYTHON@|$PYTHON|" -e "s|@BIN@|$BIN|" -e "s|@DESCARGAS@|$DESCARGAS|" \
        -e "s|@LOG@|$ESTADO/errores.log|" macos/com.gr8coolmind.ordenito.plist > "$PLIST"
    launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
    verde "✓ Servicio:  vigilando $DESCARGAS (launchd)"
else
    UNITS="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
    mkdir -p "$UNITS"
    sed "s|@DESCARGAS@|$DESCARGAS|" systemd/ordenito.path > "$UNITS/ordenito.path"
    cp systemd/ordenito.service "$UNITS/ordenito.service"
    systemctl --user daemon-reload
    systemctl --user enable --now ordenito.path >/dev/null
    verde "✓ Servicio:  vigilando $DESCARGAS (systemd)"
fi

if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    if [[ "$SISTEMA" == Darwin ]]; then
        aviso "· Para usar el comando 'ordenito':  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc"
    else
        aviso "· Agrega ~/.local/bin a tu PATH para usar el comando 'ordenito'."
    fi
fi

cat <<FIN

Listo. Todo lo que descargues se ordenará solo.
  ordenito simular            qué haría ahora mismo
  ordenito explicar ARCHIVO   por qué un archivo va a donde va
  ordenito deshacer           devuelve el último archivo movido
FIN

if [[ "$SISTEMA" == Darwin && -z "${ORDENITO_SIN_SERVICIO:-}" ]]; then
    cat <<FIN

⚠️  ÚLTIMO PASO EN MAC (una sola vez): macOS no deja que un programa en segundo plano
    lea Descargas o Documentos sin permiso. Dale "Acceso total al disco" a Python:

    1. Se abrirá Ajustes del Sistema → Privacidad y seguridad → Acceso total al disco.
    2. Pulsa "+", luego Cmd+Shift+G y pega esta ruta:
         $PYTHON
    3. Activa el interruptor que aparece.

    Si no lo haces, el servicio no podrá mover nada (verás "Operation not permitted"
    en $ESTADO/errores.log).
FIN
    open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles" 2>/dev/null || true
fi

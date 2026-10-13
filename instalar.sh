#!/usr/bin/env bash
# Instala Ordenito para tu usuario (no necesita sudo). Funciona en Linux (systemd) y macOS (launchd).
# ORDENITO_SIN_SERVICIO=1 instala sin activar el servicio (útil para pruebas).
set -euo pipefail
cd "$(dirname "$0")"

BIN="$HOME/.local/bin/ordenito"
APP_BIN="$HOME/.local/bin/ordenito-app"
DATOS="${XDG_DATA_HOME:-$HOME/.local/share}/ordenito"
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
# En Mac el servicio usa el Python de Apple si está: su ruta no cambia con 'brew upgrade', así el
# permiso de Acceso total al disco no se pierde al actualizar Homebrew.
if [[ "$SISTEMA" == Darwin ]] && xcode-select -p >/dev/null 2>&1 \
        && /usr/bin/python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
    PYTHON=/usr/bin/python3
fi
# /usr/bin/python3 es un intermediario: usamos el ejecutable real (al que se le dan los permisos)
PYTHON="$("$PYTHON" -c 'import os, sys; print(os.path.realpath(sys.executable))')"

if ! command -v pdftotext >/dev/null; then
    if [[ "$SISTEMA" == Darwin ]]; then
        aviso "· Opcional: 'brew install poppler' para que lea el contenido de los PDF."
    else
        aviso "· Opcional: instala poppler-utils (pdftotext) para que lea el contenido de los PDF."
    fi
fi

mkdir -p "$(dirname "$BIN")" "$(dirname "$CONF")" "$ESTADO" "$DATOS"
install -m 755 ordenito.py "$BIN"
verde "✓ Programa:  $BIN"

# ── La app (ventana con botones) necesita un Python con Tkinter 8.6 o más nuevo ──
python_con_tk() {
    for c in "$@"; do
        if [[ -x "$c" ]] && "$c" -c 'import sys, tkinter; sys.exit(sys.version_info < (3, 9) or tkinter.TkVersion < 8.6)' 2>/dev/null; then
            echo "$c"  # la ruta estable (enlace), no la de la versión exacta: sobrevive a actualizaciones
            return 0
        fi
    done
    return 1
}
CANDIDATOS=("$PYTHON")
for d in /opt/homebrew/bin /usr/local/bin /Library/Frameworks/Python.framework/Versions/Current/bin \
         /home/linuxbrew/.linuxbrew/bin "$HOME/.linuxbrew/bin" /usr/bin; do
    for c in "$d"/python3 "$d"/python3.[0-9]*; do  # Homebrew puede tener varias versiones
        case "$c" in *-config) continue ;; esac
        CANDIDATOS+=("$c")
    done
done
APP_PY="$(python_con_tk "${CANDIDATOS[@]}" || true)"
install -m 644 ordenito.py ordenito_app.py ordenito.png ordenito.svg "$DATOS/"
if [[ -n "$APP_PY" ]]; then
    printf '#!/bin/sh\nexec "%s" -I "%s/ordenito_app.py" "$@"\n' "$APP_PY" "$DATOS" > "$APP_BIN"
    chmod 755 "$APP_BIN"
    if [[ "$SISTEMA" == Darwin ]]; then
        APP="$HOME/Applications/Ordenito.app"
        rm -rf "$APP"
        mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
        sed "s|@VERSION@|$("$PYTHON" ordenito.py --version | cut -d' ' -f2)|" macos/Info.plist > "$APP/Contents/Info.plist"
        printf '#!/bin/sh\nexec "%s"\n' "$APP_BIN" > "$APP/Contents/MacOS/Ordenito"
        chmod 755 "$APP/Contents/MacOS/Ordenito"
        ICONOS="$(mktemp -d)/ordenito.iconset"
        mkdir -p "$ICONOS"
        for t in 16 32 128 256; do
            sips -z "$t" "$t" ordenito.png --out "$ICONOS/icon_${t}x${t}.png" >/dev/null 2>&1 || true
        done
        iconutil -c icns "$ICONOS" -o "$APP/Contents/Resources/ordenito.icns" 2>/dev/null || true
        verde "✓ App:       $APP (ábrela desde Aplicaciones o Launchpad)"
    else
        LANZADORES="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
        mkdir -p "$LANZADORES"
        sed -e "s|@APP_BIN@|$APP_BIN|" -e "s|@ICONO@|$DATOS/ordenito.png|" linux/ordenito.desktop \
            > "$LANZADORES/ordenito.desktop"
        if command -v update-desktop-database >/dev/null; then
            update-desktop-database "$LANZADORES" 2>/dev/null || true
        fi
        verde "✓ App:       búscala como \"Ordenito\" en tu menú de aplicaciones (o ejecuta ordenito-app)"
    fi
else
    if [[ "$SISTEMA" == Darwin ]]; then
        aviso "· La app con ventana necesita Tkinter: 'brew install python-tk' y vuelve a ejecutar ./instalar.sh"
    else
        aviso "· La app con ventana necesita Tkinter: instala python3-tk (Ubuntu/Debian), python3-tkinter"
        aviso "  (Fedora) o 'brew install python-tk' (Bazzite/Silverblue), y vuelve a ejecutar ./instalar.sh"
    fi
    aviso "  El servicio automático y el comando 'ordenito' funcionan igual sin ella."
fi

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
  ordenito-app                abre la ventana de Ordenito
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

#!/usr/bin/env bash
# Quita Ordenito. Tus reglas y el historial se conservan salvo que pases --todo.
set -euo pipefail
UNITS="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

systemctl --user disable --now ordenito.path 2>/dev/null || true
rm -f "$UNITS/ordenito.path" "$UNITS/ordenito.service" "$HOME/.local/bin/ordenito"
systemctl --user daemon-reload

if [[ "${1:-}" == "--todo" ]]; then
    rm -rf "${XDG_CONFIG_HOME:-$HOME/.config}/ordenito" "${XDG_STATE_HOME:-$HOME/.local/state}/ordenito"
    echo "Ordenito desinstalado, junto con tus reglas e historial."
else
    echo "Ordenito desinstalado. Tus reglas siguen en ~/.config/ordenito (bórralas con --todo)."
fi
echo "Tus archivos no se tocan: quedan donde Ordenito los dejó."

#!/usr/bin/env bash
# Quita Ordenito (Linux o macOS). Tus reglas y el historial se conservan salvo que pases --todo.
set -euo pipefail

if [[ "$(uname -s)" == Darwin ]]; then
    PLIST="$HOME/Library/LaunchAgents/com.gr8coolmind.ordenito.plist"
    launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
else
    UNITS="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
    systemctl --user disable --now ordenito.path 2>/dev/null || true
    rm -f "$UNITS/ordenito.path" "$UNITS/ordenito.service"
    systemctl --user daemon-reload
fi
rm -f "$HOME/.local/bin/ordenito" "$HOME/.local/bin/ordenito-app"
rm -rf "${XDG_DATA_HOME:-$HOME/.local/share}/ordenito" "$HOME/Applications/Ordenito.app"
rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/applications/ordenito.desktop"

if [[ "${1:-}" == "--todo" ]]; then
    rm -rf "${XDG_CONFIG_HOME:-$HOME/.config}/ordenito" "${XDG_STATE_HOME:-$HOME/.local/state}/ordenito"
    echo "Ordenito desinstalado, junto con tus reglas e historial."
else
    echo "Ordenito desinstalado. Tus reglas siguen en ~/.config/ordenito (bórralas con --todo)."
fi
echo "Tus archivos no se tocan: quedan donde Ordenito los dejó."

#!/bin/sh
# Run from the extracted portable release. Configuration is left untouched.
set -eu
bundle_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
install_dir="${XDG_DATA_HOME:-$HOME/.local/share}/killcutter-studio"
launcher_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$install_dir" "$launcher_dir"
cp -R "$bundle_dir/KillcutterStudio/." "$install_dir/"
icon_dir="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps"
mkdir -p "$icon_dir"
cp "$install_dir/_internal/killcutter/gui/assets/killcutter-256.png" "$icon_dir/killcutter-studio.png"
# Desktop Entry strings escape backslash, backtick, dollar and quote in Exec.
escaped_exec=$(printf '%s' "$install_dir/KillcutterStudio" | sed 's/[\\`$"&]/\\&/g')
cat > "$launcher_dir/killcutter-studio.desktop" <<ENTRY
[Desktop Entry]
Type=Application
Name=Killcutter Studio
Comment=Detect events and create video highlights
Exec="$escaped_exec"
Icon=killcutter-studio
StartupWMClass=KillcutterStudio
Terminal=false
Categories=AudioVideo;Video;
ENTRY
printf 'Installed to %s\nLaunch Killcutter Studio from your applications menu.\n' "$install_dir"

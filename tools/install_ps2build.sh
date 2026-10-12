#!/bin/sh
# Install ps2build (unless already present) plus the two port packages it does not ship (ogg, vorbis/vorbisfile).
# Pin with PS2DEV_INSTALL_VERSION (ps2build) and OGG_VERSION / VORBIS_VERSION (default: latest).
# PS2BUILD_TOOLCHAIN selects gcc (default), llvm, or all for the port packages.
set -e
HOST=git.techwritescode.dev
SDK="${PS2DEV_INSTALL_DIR:-$HOME/.local/share/ps2build}"

# CI installs ps2build + SDK with the setup-sdk action first; only bootstrap when it is not there yet.
if [ ! -x "$SDK/ps2build" ]; then
    curl -sSfL "https://$HOST/ps2/install/raw/branch/master/install.sh" | PS2DEV_INSTALL_DIR="$SDK" sh
fi

exec python3 "$(dirname "$0")/install_ports.py" --sdk "$SDK" --toolchain "${PS2BUILD_TOOLCHAIN:-gcc}"

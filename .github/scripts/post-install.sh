#!/bin/bash
# Post-installation script for Linux DEB package

# Create symlink in /usr/local/bin
ln -sf /opt/Open-AutoGLM-GUI/Open-AutoGLM-GUI /usr/local/bin/open-autoglm-gui

# Create desktop entry
cat > /usr/share/applications/open-autoglm-gui.desktop << EOF
[Desktop Entry]
Name=Open AutoGLM GUI
Comment=AI-powered phone automation
Exec=/opt/Open-AutoGLM-GUI/Open-AutoGLM-GUI
Terminal=false
Type=Application
Categories=Development;Utility;
EOF

echo "Open-AutoGLM-GUI installed successfully!"
echo "Run with: open-autoglm-gui"

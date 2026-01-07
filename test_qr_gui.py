#!/usr/bin/env python3
"""Test QR code pairing GUI functionality."""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/mnt/data/TOOL/Open-AutoGLM')

from PySide6 import QtWidgets, QtCore
import logging

# Set up logging to see detailed output
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def test_qr_dialog():
    """Test QR code dialog without full app."""
    app = QtWidgets.QApplication(sys.argv)
    
    try:
        from phone_agent.qr_pairing import QRCodeDialog
        
        # Create and show dialog
        dialog = QRCodeDialog()
        dialog.show()
        
        print("✅ QR Code Dialog created successfully")
        print("📱 Dialog is now visible. You can test the QR code pairing functionality.")
        print("🔍 Check the detailed logs in the dialog for Android device requests.")
        print("❌ Close the dialog window to exit the test.")
        
        # Run the application
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"❌ Error creating QR dialog: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    test_qr_dialog()

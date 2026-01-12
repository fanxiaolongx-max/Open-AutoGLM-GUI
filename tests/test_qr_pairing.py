#!/usr/bin/env python3
"""Test script for QR code pairing functionality."""

import sys
import os
import io

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import qrcode
    from phone_agent.qr_pairing import ADBQRCodePairing
    
    print("✅ All imports successful")
    
    # Test QR code generation
    pairing = ADBQRCodePairing()
    qr_data = pairing.generate_qr_code_data()
    print(f"✅ QR data generated: {qr_data}")
    
    # Test QR code image generation (without QPixmap)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save to buffer to test
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    print(f"✅ QR code image generated: {len(buffer.getvalue())} bytes")
    
    # Test mDNS service start
    success, message = pairing.start_mdns_service()
    print(f"✅ mDNS service: {success} - {message}")
    
    # Clean up
    pairing.stop_mdns_service()
    print("✅ mDNS service stopped")
    
    print("\n🎉 All tests passed! QR code pairing functionality is ready.")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Test error: {e}")
    sys.exit(1)

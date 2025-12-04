#!/usr/bin/env python3
"""
Dooya RS485 Address Programming Script
======================================

This script programs a new RS485 address on a Dooya curtain motor.

⚠️  WARNING: This will CHANGE the device address permanently!

Prerequisites:
    1. Press and hold the motor setting button for 5 seconds
    2. Wait until the LED flashes TWICE
    3. Run this script within 10 seconds

Usage:
    python test_program_address.py <new_id_low> <new_id_high>

Examples:
    # Program address to 0x1234 (ID_L=0x34, ID_H=0x12)
    python test_program_address.py 0x34 0x12
    
    # Program address to 0xFE02 (ID_L=0x02, ID_H=0xFE) 
    python test_program_address.py 0x02 0xFE

    # Using decimal values
    python test_program_address.py 2 254

Configuration:
    Edit the constants below to match your setup:
    - TCP_ADDRESS: IP address of your RS485-to-TCP gateway
    - TCP_PORT: Port number of the gateway

Notes:
    - Address bytes cannot be 0x00 or 0xFF
    - Default factory address is 0xFEFE
    - LED will flash 5 times to confirm successful programming
    - If programming fails, the device keeps its previous address

Author: shubham030
License: MIT
"""
import asyncio
import binascii
import sys

# =============================================================================
# CONFIGURATION - Edit these values to match your setup
# =============================================================================
TCP_ADDRESS = "192.168.68.200"
TCP_PORT = 502

# =============================================================================
# PROTOCOL CONSTANTS - Do not modify unless you know the protocol
# =============================================================================
START_CODE = 0x55
DEVICE_ADDRESS_SLAVE_REQUEST = 0x04
DEVICE_ADDRESS_WRITE = 0x02
DEVICE_ADDRESS_DATA_ADDR = 0x00
DEVICE_ADDRESS_DATA_LENGTH = 0x02


def calculate_crc(data: bytes) -> bytes:
    """Calculate CRC16 Modbus checksum."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc.to_bytes(2, byteorder="little")


def print_usage():
    """Print usage information."""
    print("=" * 60)
    print("Dooya RS485 Address Programming Script")
    print("=" * 60)
    print()
    print("⚠️  This will permanently change the device address!")
    print()
    print("Usage: python test_program_address.py <new_id_low> <new_id_high>")
    print()
    print("Examples:")
    print("  python test_program_address.py 0x02 0xFE  # Address 0xFE02")
    print("  python test_program_address.py 0x34 0x12  # Address 0x1234")
    print("  python test_program_address.py 2 254      # Same as 0x02 0xFE")
    print()
    print("Steps:")
    print("  1. Press and hold motor button for 5 seconds")
    print("  2. Wait for LED to flash TWICE")
    print("  3. Run this script within 10 seconds")
    print()
    print("Restrictions:")
    print("  - Address bytes cannot be 0x00 or 0xFF")
    print("  - Valid range: 1-254 (0x01-0xFE)")
    print()


async def program_address(new_id_l: int, new_id_h: int) -> bool:
    """Program new device address.
    
    Args:
        new_id_l: New low byte device ID (1-254)
        new_id_h: New high byte device ID (1-254)
        
    Returns:
        True if programming was successful
    """
    print("=" * 60)
    print("Starting Address Programming")
    print("=" * 60)
    print(f"Gateway: {TCP_ADDRESS}:{TCP_PORT}")
    print(f"New Address: 0x{new_id_h:02X}{new_id_l:02X} (ID_L=0x{new_id_l:02X}, ID_H=0x{new_id_h:02X})")
    print("=" * 60)
    
    # Validate address bytes
    if new_id_l in (0x00, 0xFF) or new_id_h in (0x00, 0xFF):
        print("❌ Error: Address bytes cannot be 0x00 or 0xFF")
        return False
    
    if not (1 <= new_id_l <= 254) or not (1 <= new_id_h <= 254):
        print("❌ Error: Address bytes must be between 1 and 254")
        return False
    
    # Connect
    print(f"\n🔌 Connecting to {TCP_ADDRESS}:{TCP_PORT}...")
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(TCP_ADDRESS, TCP_PORT),
            timeout=10.0
        )
        print("✅ Connected!")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False
    
    try:
        # Expected slave request from device after button press
        # Device sends: START(0x55) + DEFAULT_ADDR(0xFE 0xFE) + FUNC(0x04) + DATA(0x01)
        expected_start = bytes([START_CODE, 0xFE, 0xFE, DEVICE_ADDRESS_SLAVE_REQUEST])
        
        print("\n⏳ Waiting for device programming request...")
        print("   (Press and hold motor button until LED flashes twice)")
        print()
        
        # Listen for up to 30 seconds
        start_time = asyncio.get_event_loop().time()
        request_received = False
        
        while (asyncio.get_event_loop().time() - start_time) < 30:
            try:
                response = await asyncio.wait_for(reader.read(1024), timeout=1.0)
                if response:
                    print(f"📨 Received: {binascii.hexlify(response).decode().upper()}")
                    
                    if response.startswith(expected_start):
                        print("✅ Device programming request detected!")
                        request_received = True
                        break
                    else:
                        print("   (Not a programming request, waiting...)")
            except asyncio.TimeoutError:
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                print(f"   Waiting... ({elapsed}s)", end="\r")
        
        if not request_received:
            print("\n❌ Timeout: No programming request received from device")
            print("   Make sure to hold the button until LED flashes twice")
            return False
        
        # Send the new address
        print(f"\n📤 Sending new address: 0x{new_id_h:02X}{new_id_l:02X}")
        
        command = bytes([
            START_CODE,
            0x00, 0x00,  # Use 0x0000 address when programming
            DEVICE_ADDRESS_WRITE,
            DEVICE_ADDRESS_DATA_ADDR,
            DEVICE_ADDRESS_DATA_LENGTH,
            new_id_l,
            new_id_h,
        ])
        crc = calculate_crc(command)
        command += crc
        
        print(f"   Command: {binascii.hexlify(command).decode().upper()}")
        
        writer.write(command)
        await writer.drain()
        
        # Wait for confirmation
        try:
            response = await asyncio.wait_for(reader.read(1024), timeout=5.0)
            if response:
                print(f"📥 Response: {binascii.hexlify(response).decode().upper()}")
                print()
                print("=" * 60)
                print("✅ ADDRESS PROGRAMMING SUCCESSFUL!")
                print("=" * 60)
                print(f"New device address: 0x{new_id_h:02X}{new_id_l:02X}")
                print()
                print("Next steps:")
                print(f"  1. Update your Home Assistant config to use:")
                print(f"     - device_id_l: 0x{new_id_l:02X}")
                print(f"     - device_id_h: 0x{new_id_h:02X}")
                print("  2. Reload the integration")
                print()
                return True
        except asyncio.TimeoutError:
            print("⚠️  No confirmation received (may still have worked)")
            print("   Check if LED flashed 5 times on the motor")
        
        return False
        
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except:
            pass
        print("🔌 Disconnected")


async def main():
    """Main entry point."""
    if len(sys.argv) != 3:
        print_usage()
        return 1
    
    try:
        new_id_l = int(sys.argv[1], 0)
        new_id_h = int(sys.argv[2], 0)
    except ValueError:
        print("❌ Error: Invalid address format")
        print()
        print_usage()
        return 1
    
    success = await program_address(new_id_l, new_id_h)
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

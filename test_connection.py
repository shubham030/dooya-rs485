#!/usr/bin/env python3
"""
Dooya RS485 Connection Test Script
==================================

This script tests the connection to a Dooya curtain motor via RS485/TCP gateway.
It performs READ-ONLY operations and does not modify any device settings.

Usage:
    python test_connection.py [device_id_low] [device_id_high]

Examples:
    # Test with default address (0xFEFE)
    python test_connection.py

    # Test with custom address (0xFE02)
    python test_connection.py 0x02 0xFE

Configuration:
    Edit the constants below to match your setup:
    - TCP_ADDRESS: IP address of your RS485-to-TCP gateway
    - TCP_PORT: Port number of the gateway
    - DEVICE_ID_L: Low byte of device address (can be overridden via CLI)
    - DEVICE_ID_H: High byte of device address (can be overridden via CLI)

What this script tests:
    1. TCP connection to the gateway
    2. READ POSITION command (register 0x02)
    3. READ MOTOR STATUS command (register 0x05)
    4. READ DIRECTION command (register 0x03)

Output:
    - Shows raw response bytes
    - Validates CRC checksum
    - Displays position value at different byte indices to help debug

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
DEVICE_ID_L = 0xFE  # Default factory address low byte
DEVICE_ID_H = 0xFE  # Default factory address high byte

# =============================================================================
# PROTOCOL CONSTANTS - Do not modify unless you know the protocol
# =============================================================================
START_CODE = 0x55
CURTAIN_READ = 0x01
CURTAIN_READ_WRITE_PERCENT = 0x02
CURTAIN_READ_WRITE_MOTOR_STATUS = 0x05
CURTAIN_READ_WRITE_DIRECTION = 0x03


def calculate_crc(data: bytes) -> bytes:
    """Calculate CRC16 Modbus checksum.
    
    Args:
        data: Bytes to calculate CRC for
        
    Returns:
        2-byte CRC in little-endian format
    """
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


def parse_response(response: bytes, command_name: str) -> None:
    """Parse and display response bytes with detailed breakdown.
    
    Args:
        response: Raw response bytes from device
        command_name: Name of the command for display
    """
    print(f"\n{'='*60}")
    print(f"Response for: {command_name}")
    print(f"{'='*60}")
    print(f"Raw bytes ({len(response)} bytes): {binascii.hexlify(response).decode().upper()}")
    print(f"\nByte-by-byte breakdown:")
    
    labels = [
        "Start Code",
        "Device ID Low",
        "Device ID High", 
        "Function Code",
        "Data Address",
        "Data Length / Data",
        "Data Content / CRC",
        "CRC Low",
        "CRC High",
    ]
    
    for i, byte in enumerate(response):
        label = labels[i] if i < len(labels) else f"Extra byte {i}"
        print(f"  [{i}] 0x{byte:02X} ({byte:3d}) - {label}")
    
    # Validate CRC if response is long enough
    if len(response) >= 4:
        received_crc = response[-2:]
        calculated_crc = calculate_crc(response[:-2])
        crc_match = "✅ VALID" if received_crc == calculated_crc else "❌ INVALID"
        print(f"\nCRC Check: {crc_match}")
        print(f"  Received:   {binascii.hexlify(received_crc).decode().upper()}")
        print(f"  Calculated: {binascii.hexlify(calculated_crc).decode().upper()}")
    
    # Extract position if this looks like a position response
    if len(response) >= 7:
        position_at_5 = response[5]
        position_at_6 = response[6]
        print(f"\nPosition value candidates:")
        print(f"  response[5] = 0x{position_at_5:02X} ({position_at_5}%)")
        print(f"  response[6] = 0x{position_at_6:02X} ({position_at_6}%)")
        
        # Check for special values
        for idx, pos in [(5, position_at_5), (6, position_at_6)]:
            if pos == 0xFF:
                print(f"  ⚠️  response[{idx}] = 0xFF means stroke is not set")
            elif pos <= 100:
                print(f"  ✅ response[{idx}] = {pos}% is a valid position")


async def test_read_command(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    data_address: int,
    command_name: str,
) -> bytes | None:
    """Send a read command and return the response.
    
    Args:
        reader: Async stream reader
        writer: Async stream writer
        data_address: Register address to read
        command_name: Name for logging
        
    Returns:
        Response bytes or None on failure
    """
    # Build command: START + ID_L + ID_H + FUNC + ADDR + LEN + CRC
    command = bytes([
        START_CODE,
        DEVICE_ID_L,
        DEVICE_ID_H,
        CURTAIN_READ,
        data_address,
        0x01,  # Data length: 1 byte
    ])
    crc = calculate_crc(command)
    command += crc
    
    print(f"\n📤 Sending {command_name} command: {binascii.hexlify(command).decode().upper()}")
    
    try:
        writer.write(command)
        await asyncio.wait_for(writer.drain(), timeout=5.0)
        
        response = await asyncio.wait_for(reader.read(1024), timeout=5.0)
        
        if response:
            parse_response(response, command_name)
            return response
        else:
            print(f"❌ No response received for {command_name}")
            return None
            
    except asyncio.TimeoutError:
        print(f"❌ Timeout waiting for {command_name} response")
        return None


async def main():
    """Main test function."""
    print("=" * 60)
    print("Dooya RS485 Connection Test")
    print("=" * 60)
    print(f"Server: {TCP_ADDRESS}:{TCP_PORT}")
    print(f"Device Address: 0x{DEVICE_ID_H:02X}{DEVICE_ID_L:02X}")
    print("Mode: READ-ONLY (safe)")
    print("=" * 60)
    
    # Connect
    print(f"\n🔌 Connecting to {TCP_ADDRESS}:{TCP_PORT}...")
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(TCP_ADDRESS, TCP_PORT),
            timeout=10.0
        )
        print("✅ Connected successfully!")
    except asyncio.TimeoutError:
        print("❌ Connection timeout!")
        return 1
    except OSError as e:
        print(f"❌ Connection failed: {e}")
        return 1
    
    try:
        # Test 1: Read Position
        await test_read_command(reader, writer, CURTAIN_READ_WRITE_PERCENT, "READ POSITION")
        await asyncio.sleep(0.5)  # Small delay between commands
        
        # Test 2: Read Motor Status
        await test_read_command(reader, writer, CURTAIN_READ_WRITE_MOTOR_STATUS, "READ MOTOR STATUS")
        await asyncio.sleep(0.5)
        
        # Test 3: Read Direction
        await test_read_command(reader, writer, CURTAIN_READ_WRITE_DIRECTION, "READ DIRECTION")
        
        print("\n" + "=" * 60)
        print("✅ Test completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        return 1
    finally:
        print("\n🔌 Closing connection...")
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=2.0)
        except asyncio.TimeoutError:
            pass
        print("Connection closed.")
    
    return 0


if __name__ == "__main__":
    # Allow overriding device address from command line
    if len(sys.argv) >= 3:
        try:
            DEVICE_ID_L = int(sys.argv[1], 0)
            DEVICE_ID_H = int(sys.argv[2], 0)
            print(f"Using custom device address: 0x{DEVICE_ID_H:02X}{DEVICE_ID_L:02X}")
        except ValueError:
            print("Usage: python test_connection.py [device_id_low] [device_id_high]")
            print("Example: python test_connection.py 0xFE 0xFE")
            print("         python test_connection.py 0x02 0xFE")
            sys.exit(1)
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

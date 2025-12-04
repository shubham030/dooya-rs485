#!/usr/bin/env python3
"""
Dooya RS485 Control & Monitor Test Script
=========================================

This script allows you to control and monitor a Dooya curtain motor via RS485/TCP gateway.
It can send OPEN, CLOSE, STOP commands and monitor position in real-time.

⚠️  WARNING: This script sends CONTROL commands that will MOVE your curtain!

Usage:
    python test_set_stroke.py [action]

Actions:
    open    - Open the curtain fully and monitor position
    close   - Close the curtain fully and monitor position
    stop    - Send stop command immediately
    monitor - Monitor position only (no commands sent)

Examples:
    python test_set_stroke.py open
    python test_set_stroke.py close
    python test_set_stroke.py monitor

Configuration:
    Edit the constants below to match your setup:
    - TCP_ADDRESS: IP address of your RS485-to-TCP gateway
    - TCP_PORT: Port number of the gateway
    - DEVICE_ID_L: Low byte of device address
    - DEVICE_ID_H: High byte of device address

Notes:
    - If position shows 0xFF, the motor stroke is not set
    - Running a full open+close cycle usually sets the stroke
    - Press Ctrl+C to stop the curtain and exit

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
DEVICE_ID_L = 0x02
DEVICE_ID_H = 0xFE

# =============================================================================
# PROTOCOL CONSTANTS - Do not modify unless you know the protocol
# =============================================================================
START_CODE = 0x55
CURTAIN_READ = 0x01
CURTAIN_COMMAND = 0x03
CURTAIN_COMMAND_OPEN = 0x01
CURTAIN_COMMAND_CLOSE = 0x02
CURTAIN_COMMAND_STOP = 0x03
CURTAIN_READ_WRITE_PERCENT = 0x02


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


async def send_command(writer, reader, cmd_bytes: bytes, name: str) -> bytes | None:
    """Send a command and get response.
    
    Args:
        writer: Async stream writer
        reader: Async stream reader
        cmd_bytes: Command bytes (without START, ID, or CRC)
        name: Command name for logging
        
    Returns:
        Response bytes or None on failure
    """
    command = bytes([START_CODE, DEVICE_ID_L, DEVICE_ID_H]) + cmd_bytes
    command += calculate_crc(command)
    
    print(f"📤 {name}: {binascii.hexlify(command).decode().upper()}")
    writer.write(command)
    await writer.drain()
    
    try:
        response = await asyncio.wait_for(reader.read(1024), timeout=3.0)
        print(f"📥 Response: {binascii.hexlify(response).decode().upper()}")
        return response
    except asyncio.TimeoutError:
        print("   ⏱️ No response (timeout)")
        return None


async def read_position(writer, reader) -> int | None:
    """Read current position.
    
    Args:
        writer: Async stream writer
        reader: Async stream reader
        
    Returns:
        Position (0-100) or 0xFF if stroke not set, None on failure
    """
    command = bytes([START_CODE, DEVICE_ID_L, DEVICE_ID_H, CURTAIN_READ, CURTAIN_READ_WRITE_PERCENT, 0x01])
    command += calculate_crc(command)
    
    writer.write(command)
    await writer.drain()
    
    try:
        response = await asyncio.wait_for(reader.read(1024), timeout=3.0)
        if len(response) >= 6:
            pos = response[5]
            return pos
    except asyncio.TimeoutError:
        pass
    return None


async def monitor_position(writer, reader, duration: int = 30) -> int | None:
    """Monitor position for a duration with visual progress bar.
    
    Args:
        writer: Async stream writer
        reader: Async stream reader
        duration: How long to monitor in seconds
        
    Returns:
        Last position value
    """
    print(f"\n📊 Monitoring position for {duration} seconds...")
    print("-" * 40)
    
    start = asyncio.get_event_loop().time()
    last_pos = None
    
    while (asyncio.get_event_loop().time() - start) < duration:
        pos = await read_position(writer, reader)
        elapsed = int(asyncio.get_event_loop().time() - start)
        
        if pos != last_pos:
            if pos == 0xFF:
                print(f"[{elapsed:2d}s] Position: 0xFF (stroke not set)")
            elif pos is not None:
                bar = "█" * (pos // 5) + "░" * (20 - pos // 5)
                print(f"[{elapsed:2d}s] Position: {pos:3d}% |{bar}|")
            last_pos = pos
        
        await asyncio.sleep(0.5)
    
    print("-" * 40)
    return last_pos


def print_usage():
    """Print usage information."""
    print("=" * 60)
    print("Dooya RS485 Control & Monitor Script")
    print("=" * 60)
    print()
    print("Usage: python test_set_stroke.py [action]")
    print()
    print("Actions:")
    print("  open    - Open the curtain fully")
    print("  close   - Close the curtain fully")
    print("  stop    - Stop the curtain immediately")
    print("  monitor - Monitor position only (no movement)")
    print()
    print(f"Current config:")
    print(f"  Address: {TCP_ADDRESS}:{TCP_PORT}")
    print(f"  Device:  0x{DEVICE_ID_H:02X}{DEVICE_ID_L:02X}")
    print()


async def main():
    """Main function."""
    action = sys.argv[1] if len(sys.argv) > 1 else "monitor"
    
    if action not in ["open", "close", "stop", "monitor"]:
        print_usage()
        print(f"❌ Unknown action: {action}")
        return 1
    
    print_usage()
    print(f"Action: {action.upper()}")
    print("=" * 60)
    
    # Connect
    try:
        reader, writer = await asyncio.open_connection(TCP_ADDRESS, TCP_PORT)
        print("✅ Connected!\n")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return 1
    
    try:
        # Read initial position
        pos = await read_position(writer, reader)
        if pos == 0xFF:
            print(f"Initial position: 0xFF (stroke not set)")
        elif pos is not None:
            print(f"Initial position: {pos}%")
        else:
            print("Initial position: unknown")
        
        # Execute action
        if action == "open":
            print("\n🔼 OPENING curtain...")
            await send_command(writer, reader, bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_OPEN]), "OPEN")
            await monitor_position(writer, reader, 45)
            
        elif action == "close":
            print("\n🔽 CLOSING curtain...")
            await send_command(writer, reader, bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_CLOSE]), "CLOSE")
            await monitor_position(writer, reader, 45)
            
        elif action == "stop":
            print("\n⏹️ STOPPING curtain...")
            await send_command(writer, reader, bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_STOP]), "STOP")
            
        elif action == "monitor":
            print("\n👁️ Monitoring only (no commands)...")
            await monitor_position(writer, reader, 60)
        
        # Final position check
        print("\n" + "=" * 60)
        print("Final position check:")
        pos = await read_position(writer, reader)
        if pos == 0xFF:
            print("⚠️  Position shows 0xFF (stroke not set)")
            print("   Run 'open' then 'close' to set the stroke.")
        elif pos is not None:
            print(f"✅ Position: {pos}%")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted! Sending STOP...")
        await send_command(writer, reader, bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_STOP]), "STOP")
    finally:
        writer.close()
        await writer.wait_closed()
        print("\n🔌 Disconnected.")
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

"""API for controlling Dooya curtain motor."""
import asyncio
import socket
import binascii
import logging

from .const import *

_LOGGER = logging.getLogger(__name__)

class DooyaController:
    """Class to control Dooya curtain motor."""

    def __init__(self, tcp_port, tcp_address, device_id_l, device_id_h):
        """Initialize the controller."""
        _LOGGER.info(
            "Initializing DooyaController with: tcp_port=%s, tcp_address=%s, device_id_l=0x%02X, device_id_h=0x%02X",
            tcp_port,
            tcp_address,
            device_id_l,
            device_id_h
        )
        self.tcp_port = tcp_port
        self.tcp_address = tcp_address
        self.device_id_l = device_id_l
        self.device_id_h = device_id_h
        self._reader = None
        self._writer = None
        self._lock = asyncio.Lock()
        _LOGGER.debug("Controller initialized successfully")

    async def connect(self):
        """Connect to the TCP server."""
        _LOGGER.info("Attempting to connect to %s:%s", self.tcp_address, self.tcp_port)
        try:
            self._reader, self._writer = await asyncio.open_connection(
                self.tcp_address, self.tcp_port
            )
            _LOGGER.info("Successfully connected to %s:%s", self.tcp_address, self.tcp_port)
        except Exception as e:
            _LOGGER.error("Failed to connect to %s:%s - %s", self.tcp_address, self.tcp_port, e)
            raise

    async def disconnect(self):
        """Disconnect from the TCP server."""
        _LOGGER.info("Disconnecting from %s:%s", self.tcp_address, self.tcp_port)
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
            self._reader = None
            self._writer = None
            _LOGGER.info("Successfully disconnected")

    async def open(self):
        """Open the curtain."""
        _LOGGER.debug("Sending open command")
        rs485_command = bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_OPEN])
        response = await self.send_rs485_command(rs485_command)
        return response

    async def close(self):
        """Close the curtain."""
        _LOGGER.debug("Sending close command")
        rs485_command = bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_CLOSE])
        response = await self.send_rs485_command(rs485_command)
        return response

    async def stop(self):
        """Stop the curtain."""
        _LOGGER.debug("Sending stop command")
        rs485_command = bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_STOP])
        response = await self.send_rs485_command(rs485_command)
        return response
    
    async def set_cover_position(self, position):
        """Set the cover position."""
        _LOGGER.debug("Setting cover position to %d%%", position)
        rs485_command = bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_PERCENT, position])
        response = await self.send_rs485_command(rs485_command)
        return response

    async def read_cover_position(self):
        """Read the cover position."""
        try:
            _LOGGER.debug("Reading cover position")
            rs485_command = bytes([CURTAIN_READ, CURTAIN_READ_WRITE_PERCENT, 0x01])
            response = await self.send_rs485_command(rs485_command)
            
            if response is None or len(response) < 6:
                _LOGGER.error("Invalid response received from device")
                return 255  # Return unknown position
                
            position = response[5]
            _LOGGER.debug("Cover position read: %d%%", position)
            return position
        except Exception as e:
            _LOGGER.error("Error reading cover position: %s", e)
            return 255  # Return unknown position

    async def read_cover_direction(self):
        """Read the cover direction."""
        try:
            _LOGGER.debug("Reading cover direction")
            rs485_command = bytes([CURTAIN_READ, CURTAIN_READ_WRITE_DIRECTION, 0x01])
            response = await self.send_rs485_command(rs485_command)
            
            if response is None or len(response) < 6:
                _LOGGER.error("Invalid response received from device")
                return None
                
            direction = response[5]
            _LOGGER.debug("Cover direction read: 0x%02X", direction)
            return direction
        except Exception as e:
            _LOGGER.error("Error reading cover direction: %s", e)
            return None

    async def send_rs485_command(self, rs485_command):
        """Send RS485 command over TCP."""
        async with self._lock:
            try:
                # Ensure we're connected
                if not self._writer:
                    _LOGGER.debug("No active connection, attempting to connect")
                    await self.connect()

                # Construct full command
                full_command = bytes([START_CODE, self.device_id_l, self.device_id_h]) + rs485_command
                # Append CRC to RS485 command
                crc = self.calculate_crc(full_command)
                full_command += crc

                _LOGGER.debug(
                    "Sending command: %s",
                    binascii.hexlify(full_command).decode()
                )

                # Send the full command
                self._writer.write(full_command)
                await self._writer.drain()

                # Receive response (if any)
                response = await self._reader.read(1024)
                if not response:
                    _LOGGER.error("No response received from device")
                    return None
                    
                _LOGGER.debug(
                    "Response received: %s",
                    binascii.hexlify(response).decode()
                )
                return response
                    
            except Exception as e:
                _LOGGER.error("Error sending RS485 command: %s", e)
                # Try to reconnect on next command
                await self.disconnect()
                return None

    def calculate_crc(self, data):
        """Calculate CRC."""
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc >>= 1
                    crc ^= 0xA001
                else:
                    crc >>= 1
        return crc.to_bytes(2, byteorder='little')
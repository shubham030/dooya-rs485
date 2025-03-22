"""API for controlling Dooya curtain motor."""
import asyncio
import socket
import binascii
import logging

from .const import (
    START_CODE,
    CURTAIN_READ,
    CURTAIN_WRITE,
    CURTAIN_COMMAND,
    CURTAIN_COMMAND_OPEN,
    CURTAIN_COMMAND_CLOSE,
    CURTAIN_COMMAND_STOP,
    CURTAIN_COMMAND_PERCENT,
    CURTAIN_COMMAND_DELETE,
    CURTAIN_COMMAND_RESET,
    CURTAIN_READ_WRITE_PERCENT,
    CURTAIN_READ_WRITE_DIRECTION,
    CURTAIN_READ_WRITE_HANDLE,
    CURTAIN_READ_WRITE_MOTOR_STATUS,
    CURTAIN_READ_WRITE_SWITCH_PASSIVE,
    CURTAIN_READ_WRITE_SWITCH_ACTIVE,
    CURTAIN_READ_WRITE_VERSION,
    DEVICE_ADDRESS_SLAVE_REQUEST,
    DEVICE_ADDRESS_WRITE,
    DEVICE_ADDRESS_DATA_ADDR,
    DEVICE_ADDRESS_DATA_LENGTH,
)

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
            
            if response is None:
                _LOGGER.error("No response received from device")
                return None
                
            # Handle status-only response
            if len(response) == 2:
                _LOGGER.warning("Received status-only response for position read")
                return None
                
            # Handle data response
            if len(response) < 6:
                _LOGGER.error("Invalid response length for position read: %d", len(response))
                return None
                
            position = response[5]
            _LOGGER.debug("Raw position from device: 0x%02X", position)
            
            # Handle case where stroke is not set (0xFF)
            if position == 0xFF:
                _LOGGER.warning("Device reports stroke is not set")
                return None
                
            # Position should be between 0x00 (fully closed) and 0x64 (fully open)
            if position > 0x64:
                _LOGGER.error("Invalid position value received: 0x%02X", position)
                return None
                
            _LOGGER.debug("Cover position read: %d%%", position)
            return position
        except Exception as e:
            _LOGGER.error("Error reading cover position: %s", e)
            return None

    async def read_cover_direction(self):
        """Read the cover direction."""
        try:
            _LOGGER.debug("Reading cover direction")
            rs485_command = bytes([CURTAIN_READ, CURTAIN_READ_WRITE_DIRECTION, 0x01])
            response = await self.send_rs485_command(rs485_command)
            
            if response is None:
                _LOGGER.error("No response received from device")
                return None
                
            # Handle status-only response
            if len(response) == 2:
                _LOGGER.warning("Received status-only response for direction read")
                return None
                
            # Handle data response
            if len(response) < 6:
                _LOGGER.error("Invalid response length for direction read: %d", len(response))
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

                # Set a timeout for reading the response
                try:
                    response = await asyncio.wait_for(self._reader.read(1024), timeout=5.0)
                except asyncio.TimeoutError:
                    _LOGGER.error("Timeout waiting for device response")
                    return None

                if not response:
                    _LOGGER.error("No response received from device")
                    return None
                
                # Log raw response for debugging
                _LOGGER.debug(
                    "Raw response received: %s",
                    binascii.hexlify(response).decode()
                )
                
                # Basic response validation
                if len(response) < 2:  # Minimum response is just status
                    _LOGGER.error("Response too short: %d bytes", len(response))
                    return None
                
                # Check if response is just a status (2 bytes)
                if len(response) == 2:
                    _LOGGER.debug("Received status-only response")
                    return response
                
                # For longer responses, validate CRC
                if len(response) >= 4:  # Response with data should have CRC
                    received_crc = response[-2:]
                    calculated_crc = self.calculate_crc(response[:-2])
                    if received_crc != calculated_crc:
                        _LOGGER.error(
                            "CRC mismatch - Received: %s, Calculated: %s",
                            binascii.hexlify(received_crc).decode(),
                            binascii.hexlify(calculated_crc).decode()
                        )
                        return None
                
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

    async def read_motor_status(self):
        """Read the motor status."""
        try:
            _LOGGER.debug("Reading motor status")
            rs485_command = bytes([CURTAIN_READ, CURTAIN_READ_WRITE_MOTOR_STATUS, 0x01])
            response = await self.send_rs485_command(rs485_command)
            
            if response is None:
                _LOGGER.error("No response received from device")
                return None
                
            # Handle status-only response
            if len(response) == 2:
                _LOGGER.warning("Received status-only response for motor status read")
                return None
                
            # Handle data response
            if len(response) < 6:
                _LOGGER.error("Invalid response length for motor status read: %d", len(response))
                return None
                
            status = response[5]
            _LOGGER.debug("Motor status read: 0x%02X", status)
            return status
        except Exception as e:
            _LOGGER.error("Error reading motor status: %s", e)
            return None

    async def read_switch_status(self):
        """Read both active and passive switch status."""
        try:
            _LOGGER.debug("Reading switch status")
            active_cmd = bytes([CURTAIN_READ, CURTAIN_READ_WRITE_SWITCH_ACTIVE, 0x01])
            passive_cmd = bytes([CURTAIN_READ, CURTAIN_READ_WRITE_SWITCH_PASSIVE, 0x01])
            
            active_response = await self.send_rs485_command(active_cmd)
            passive_response = await self.send_rs485_command(passive_cmd)
            
            if active_response is None or passive_response is None:
                _LOGGER.error("No response received from device")
                return None, None
                
            # Handle status-only responses
            if len(active_response) == 2 or len(passive_response) == 2:
                _LOGGER.warning("Received status-only response for switch status read")
                return None, None
                
            # Handle data responses
            if len(active_response) < 6 or len(passive_response) < 6:
                _LOGGER.error("Invalid response length for switch status read")
                return None, None
                
            active_status = active_response[5]
            passive_status = passive_response[5]
            _LOGGER.debug("Switch status read - Active: 0x%02X, Passive: 0x%02X", active_status, passive_status)
            return active_status, passive_status
        except Exception as e:
            _LOGGER.error("Error reading switch status: %s", e)
            return None, None

    async def read_version(self):
        """Read the device version."""
        try:
            _LOGGER.debug("Reading device version")
            rs485_command = bytes([CURTAIN_READ, CURTAIN_READ_WRITE_VERSION, 0x01])
            response = await self.send_rs485_command(rs485_command)
            
            if response is None:
                _LOGGER.error("No response received from device")
                return None
                
            # Handle status-only response
            if len(response) == 2:
                _LOGGER.warning("Received status-only response for version read")
                return None
                
            # Handle data response
            if len(response) < 6:
                _LOGGER.error("Invalid response length for version read: %d", len(response))
                return None
                
            version = response[5]
            _LOGGER.debug("Device version read: 0x%02X", version)
            return version
        except Exception as e:
            _LOGGER.error("Error reading device version: %s", e)
            return None

    async def read_handle_status(self):
        """Read the handle status."""
        try:
            _LOGGER.debug("Reading handle status")
            rs485_command = bytes([CURTAIN_READ, CURTAIN_READ_WRITE_HANDLE, 0x01])
            response = await self.send_rs485_command(rs485_command)
            
            if response is None:
                _LOGGER.error("No response received from device")
                return None
                
            # Handle status-only response
            if len(response) == 2:
                _LOGGER.warning("Received status-only response for handle status read")
                return None
                
            # Handle data response
            if len(response) < 6:
                _LOGGER.error("Invalid response length for handle status read: %d", len(response))
                return None
                
            status = response[5]
            _LOGGER.debug("Handle status read: 0x%02X", status)
            return status
        except Exception as e:
            _LOGGER.error("Error reading handle status: %s", e)
            return None

    async def reset(self):
        """Reset the device."""
        _LOGGER.debug("Sending reset command")
        rs485_command = bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_RESET])
        response = await self.send_rs485_command(rs485_command)
        return response

    async def delete(self):
        """Delete the device configuration."""
        _LOGGER.debug("Sending delete command")
        rs485_command = bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_DELETE])
        response = await self.send_rs485_command(rs485_command)
        return response

    async def program_device_address(self, new_id_l: int, new_id_h: int) -> bool:
        """Program new device address after button is pressed and held.
        
        Args:
            new_id_l: New low byte device ID (cannot be 0x00 or 0xFF)
            new_id_h: New high byte device ID (cannot be 0x00 or 0xFF)
        
        Returns:
            bool: True if programming was successful
        """
        _LOGGER.info(
            "Programming new device address: ID_L=0x%02X, ID_H=0x%02X",
            new_id_l,
            new_id_h
        )
        
        # Validate address bytes
        if new_id_l in (0x00, 0xFF) or new_id_h in (0x00, 0xFF):
            _LOGGER.error("Invalid address bytes. Cannot be 0x00 or 0xFF")
            return False

        try:
            # Wait for slave request (0x04) after button press
            # Default address (0xFEFE) + Function (0x04) + Data addr (0x01)
            expected_request = bytes([
                START_CODE,
                0xFE, 0xFE,
                DEVICE_ADDRESS_SLAVE_REQUEST,
                0x01
            ])
            
            # Listen for the request for up to 10 seconds
            start_time = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start_time) < 10:
                try:
                    response = await asyncio.wait_for(
                        self._reader.read(1024),
                        timeout=1.0
                    )
                    if response and response.startswith(expected_request):
                        _LOGGER.debug("Received slave programming request")
                        break
                except asyncio.TimeoutError:
                    continue
            else:
                _LOGGER.error("Timeout waiting for slave programming request")
                return False

            # Send write address command
            command = bytes([
                START_CODE,
                0x00, 0x00,    # Use 0x0000 when programming
                DEVICE_ADDRESS_WRITE,
                DEVICE_ADDRESS_DATA_ADDR,
                DEVICE_ADDRESS_DATA_LENGTH,
                new_id_l,
                new_id_h
            ])
            
            # Add CRC
            crc = self.calculate_crc(command)
            command += crc
            
            _LOGGER.debug(
                "Sending address programming command: %s",
                binascii.hexlify(command).decode()
            )
            
            self._writer.write(command)
            await self._writer.drain()
            
            # Wait for confirmation response
            try:
                response = await asyncio.wait_for(
                    self._reader.read(1024),
                    timeout=5.0
                )
                if response:
                    _LOGGER.info("Address programming successful")
                    # Update controller's stored address
                    self.device_id_l = new_id_l
                    self.device_id_h = new_id_h
                    return True
            except asyncio.TimeoutError:
                _LOGGER.error("Timeout waiting for programming confirmation")
            
            return False
            
        except Exception as e:
            _LOGGER.error("Error during address programming: %s", e)
            return False
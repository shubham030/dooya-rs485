"""API for controlling Dooya curtain motor."""
import asyncio
import binascii
import logging
from typing import Optional, Tuple

from .const import (
    START_CODE,
    CURTAIN_READ,
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

# Timeout constants
CONNECTION_TIMEOUT = 10.0  # Timeout for establishing connection
COMMAND_TIMEOUT = 5.0  # Timeout for command response
RECONNECT_DELAY = 2.0  # Delay between reconnection attempts
MAX_RETRIES = 3  # Maximum number of retries for commands


class DooyaController:
    """Class to control Dooya curtain motor."""

    def __init__(self, tcp_port: int, tcp_address: str, device_id_l: int, device_id_h: int):
        """Initialize the controller."""
        _LOGGER.info(
            "Initializing DooyaController with: tcp_port=%s, tcp_address=%s, device_id_l=0x%02X, device_id_h=0x%02X",
            tcp_port,
            tcp_address,
            device_id_l,
            device_id_h,
        )
        self.tcp_port = tcp_port
        self.tcp_address = tcp_address
        self.device_id_l = device_id_l
        self.device_id_h = device_id_h
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._lock = asyncio.Lock()
        self._connected = False
        self._connecting = False
        _LOGGER.debug("Controller initialized successfully")

    @property
    def is_connected(self) -> bool:
        """Return True if connected to the device."""
        return self._connected and self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> bool:
        """Connect to the TCP server with timeout."""
        if self._connecting:
            _LOGGER.debug("Connection already in progress, waiting...")
            # Wait for the ongoing connection attempt to finish
            for _ in range(50):  # Wait up to 5 seconds
                await asyncio.sleep(0.1)
                if not self._connecting:
                    return self.is_connected
            return False

        self._connecting = True
        try:
            _LOGGER.info("Attempting to connect to %s:%s", self.tcp_address, self.tcp_port)
            
            # Clean up any existing connection first
            await self._cleanup_connection()
            
            # Connect with timeout
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.tcp_address, self.tcp_port),
                timeout=CONNECTION_TIMEOUT,
            )
            self._connected = True
            _LOGGER.info("Successfully connected to %s:%s", self.tcp_address, self.tcp_port)
            return True
            
        except asyncio.TimeoutError:
            _LOGGER.error("Connection timeout to %s:%s", self.tcp_address, self.tcp_port)
            self._connected = False
            return False
        except OSError as e:
            _LOGGER.error("Connection failed to %s:%s: %s", self.tcp_address, self.tcp_port, e)
            self._connected = False
            return False
        except Exception as e:
            _LOGGER.error("Unexpected error connecting to %s:%s: %s", self.tcp_address, self.tcp_port, e)
            self._connected = False
            return False
        finally:
            self._connecting = False

    async def _cleanup_connection(self) -> None:
        """Clean up existing connection resources."""
        if self._writer is not None:
            try:
                self._writer.close()
                # Use wait_for to prevent hanging on wait_closed
                await asyncio.wait_for(self._writer.wait_closed(), timeout=2.0)
            except asyncio.TimeoutError:
                _LOGGER.warning("Timeout while closing connection")
            except Exception as e:
                _LOGGER.debug("Error during connection cleanup: %s", e)
            finally:
                self._reader = None
                self._writer = None
                self._connected = False

    async def ensure_connected(self) -> bool:
        """Ensure connection is active, reconnect if necessary."""
        if self.is_connected:
            return True
        
        _LOGGER.info("Connection lost or not established, attempting to reconnect")
        return await self.connect()

    async def disconnect(self) -> None:
        """Disconnect from the TCP server."""
        _LOGGER.info("Disconnecting from %s:%s", self.tcp_address, self.tcp_port)
        await self._cleanup_connection()
        _LOGGER.info("Successfully disconnected")

    async def open(self) -> Optional[bytes]:
        """Open the curtain."""
        _LOGGER.debug("Sending open command")
        rs485_command = bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_OPEN])
        return await self._send_command_with_retry(rs485_command)

    async def close(self) -> Optional[bytes]:
        """Close the curtain."""
        _LOGGER.debug("Sending close command")
        rs485_command = bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_CLOSE])
        return await self._send_command_with_retry(rs485_command)

    async def stop(self) -> Optional[bytes]:
        """Stop the curtain."""
        _LOGGER.debug("Sending stop command")
        rs485_command = bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_STOP])
        return await self._send_command_with_retry(rs485_command)

    async def set_cover_position(self, position: int) -> Optional[bytes]:
        """Set the cover position."""
        _LOGGER.debug("Setting cover position to %d%%", position)
        rs485_command = bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_PERCENT, position])
        return await self._send_command_with_retry(rs485_command)

    async def read_cover_position(self) -> Optional[int]:
        """Read the cover position."""
        try:
            _LOGGER.debug("Reading cover position")
            rs485_command = bytes([CURTAIN_READ, CURTAIN_READ_WRITE_PERCENT, 0x01])
            response = await self._send_command_with_retry(rs485_command)

            if response is None:
                _LOGGER.debug("No response received from device for position read")
                return None

            # Handle status-only response
            if len(response) == 2:
                _LOGGER.debug("Received status-only response for position read")
                return None

            # Handle data response
            if len(response) < 6:
                _LOGGER.debug("Invalid response length for position read: %d", len(response))
                return None

            position = response[5]
            _LOGGER.debug("Raw position from device: 0x%02X", position)

            # Handle case where stroke is not set (0xFF)
            if position == 0xFF:
                _LOGGER.warning("Device reports stroke is not set")
                return None

            # Position should be between 0x00 (fully closed) and 0x64 (fully open)
            if position > 0x64:
                _LOGGER.debug("Invalid position value received: 0x%02X", position)
                return None

            _LOGGER.debug("Cover position read: %d%%", position)
            return position
        except Exception as e:
            _LOGGER.error("Error reading cover position: %s", e)
            return None

    async def read_cover_direction(self) -> Optional[int]:
        """Read the cover direction."""
        try:
            _LOGGER.debug("Reading cover direction")
            rs485_command = bytes([CURTAIN_READ, CURTAIN_READ_WRITE_DIRECTION, 0x01])
            response = await self._send_command_with_retry(rs485_command)

            if response is None:
                _LOGGER.debug("No response received from device for direction read")
                return None

            # Handle status-only response
            if len(response) == 2:
                _LOGGER.debug("Received status-only response for direction read")
                return None

            # Handle data response
            if len(response) < 6:
                _LOGGER.debug("Invalid response length for direction read: %d", len(response))
                return None

            direction = response[5]
            _LOGGER.debug("Cover direction read: 0x%02X", direction)
            return direction
        except Exception as e:
            _LOGGER.error("Error reading cover direction: %s", e)
            return None

    async def _send_command_with_retry(self, rs485_command: bytes) -> Optional[bytes]:
        """Send RS485 command with automatic retry on failure."""
        for attempt in range(MAX_RETRIES):
            try:
                response = await self.send_rs485_command(rs485_command)
                if response is not None:
                    return response
                
                if attempt < MAX_RETRIES - 1:
                    _LOGGER.debug("Command failed, retrying (attempt %d/%d)", attempt + 2, MAX_RETRIES)
                    await asyncio.sleep(RECONNECT_DELAY)
            except Exception as e:
                _LOGGER.debug("Command attempt %d failed: %s", attempt + 1, e)
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RECONNECT_DELAY)
        
        _LOGGER.warning("Command failed after %d attempts", MAX_RETRIES)
        return None

    async def send_rs485_command(self, rs485_command: bytes) -> Optional[bytes]:
        """Send RS485 command over TCP with connection handling."""
        # Use timeout for acquiring lock to prevent deadlock
        try:
            async with asyncio.timeout(CONNECTION_TIMEOUT):
                async with self._lock:
                    return await self._send_rs485_command_locked(rs485_command)
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout waiting to acquire lock for command")
            return None

    async def _send_rs485_command_locked(self, rs485_command: bytes) -> Optional[bytes]:
        """Send RS485 command (must be called with lock held)."""
        try:
            # Ensure we're connected
            if not await self.ensure_connected():
                _LOGGER.error("Failed to establish connection")
                return None

            # Construct full command
            full_command = bytes([START_CODE, self.device_id_l, self.device_id_h]) + rs485_command
            # Append CRC to RS485 command
            crc = self.calculate_crc(full_command)
            full_command += crc

            _LOGGER.debug("Sending command: %s", binascii.hexlify(full_command).decode())

            # Send the full command
            self._writer.write(full_command)
            await asyncio.wait_for(self._writer.drain(), timeout=COMMAND_TIMEOUT)

            # Read response with timeout
            try:
                response = await asyncio.wait_for(
                    self._reader.read(1024),
                    timeout=COMMAND_TIMEOUT,
                )
                if not response:
                    _LOGGER.warning("Empty response received")
                    await self._cleanup_connection()
                    return None
            except asyncio.TimeoutError:
                _LOGGER.warning("Timeout waiting for response")
                await self._cleanup_connection()
                return None

            # Log raw response for debugging
            _LOGGER.debug("Raw response received: %s", binascii.hexlify(response).decode())

            # Basic response validation
            if len(response) < 2:  # Minimum response is just status
                _LOGGER.debug("Response too short: %d bytes", len(response))
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
                    _LOGGER.warning(
                        "CRC mismatch - Received: %s, Calculated: %s",
                        binascii.hexlify(received_crc).decode(),
                        binascii.hexlify(calculated_crc).decode(),
                    )
                    return None

            return response

        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout during command send/receive")
            await self._cleanup_connection()
            return None
        except (ConnectionError, OSError) as e:
            _LOGGER.warning("Connection error: %s", e)
            await self._cleanup_connection()
            return None
        except Exception as e:
            _LOGGER.error("Unexpected error sending RS485 command: %s", e)
            await self._cleanup_connection()
            return None

    def calculate_crc(self, data: bytes) -> bytes:
        """Calculate CRC16 Modbus."""
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

    async def read_motor_status(self) -> Optional[int]:
        """Read the motor status."""
        try:
            _LOGGER.debug("Reading motor status")
            rs485_command = bytes([CURTAIN_READ, CURTAIN_READ_WRITE_MOTOR_STATUS, 0x01])
            response = await self._send_command_with_retry(rs485_command)

            if response is None:
                _LOGGER.debug("No response received from device for motor status")
                return None

            # Handle status-only response
            if len(response) == 2:
                _LOGGER.debug("Received status-only response for motor status read")
                return None

            # Handle data response
            if len(response) < 6:
                _LOGGER.debug("Invalid response length for motor status read: %d", len(response))
                return None

            status = response[5]
            _LOGGER.debug("Motor status read: 0x%02X", status)
            return status
        except Exception as e:
            _LOGGER.error("Error reading motor status: %s", e)
            return None

    async def read_switch_status(self) -> Tuple[Optional[int], Optional[int]]:
        """Read both active and passive switch status."""
        try:
            _LOGGER.debug("Reading switch status")
            active_cmd = bytes([CURTAIN_READ, CURTAIN_READ_WRITE_SWITCH_ACTIVE, 0x01])
            passive_cmd = bytes([CURTAIN_READ, CURTAIN_READ_WRITE_SWITCH_PASSIVE, 0x01])

            active_response = await self._send_command_with_retry(active_cmd)
            passive_response = await self._send_command_with_retry(passive_cmd)

            active_status = None
            passive_status = None

            if active_response is not None and len(active_response) >= 6:
                active_status = active_response[5]
            if passive_response is not None and len(passive_response) >= 6:
                passive_status = passive_response[5]

            _LOGGER.debug(
                "Switch status read - Active: %s, Passive: %s",
                f"0x{active_status:02X}" if active_status is not None else "None",
                f"0x{passive_status:02X}" if passive_status is not None else "None",
            )
            return active_status, passive_status
        except Exception as e:
            _LOGGER.error("Error reading switch status: %s", e)
            return None, None

    async def read_version(self) -> Optional[int]:
        """Read the device version."""
        try:
            _LOGGER.debug("Reading device version")
            rs485_command = bytes([CURTAIN_READ, CURTAIN_READ_WRITE_VERSION, 0x01])
            response = await self._send_command_with_retry(rs485_command)

            if response is None:
                _LOGGER.debug("No response received from device for version")
                return None

            # Handle status-only response
            if len(response) == 2:
                _LOGGER.debug("Received status-only response for version read")
                return None

            # Handle data response
            if len(response) < 6:
                _LOGGER.debug("Invalid response length for version read: %d", len(response))
                return None

            version = response[5]
            _LOGGER.debug("Device version read: 0x%02X", version)
            return version
        except Exception as e:
            _LOGGER.error("Error reading device version: %s", e)
            return None

    async def read_handle_status(self) -> Optional[int]:
        """Read the handle status."""
        try:
            _LOGGER.debug("Reading handle status")
            rs485_command = bytes([CURTAIN_READ, CURTAIN_READ_WRITE_HANDLE, 0x01])
            response = await self._send_command_with_retry(rs485_command)

            if response is None:
                _LOGGER.debug("No response received from device for handle status")
                return None

            # Handle status-only response
            if len(response) == 2:
                _LOGGER.debug("Received status-only response for handle status read")
                return None

            # Handle data response
            if len(response) < 6:
                _LOGGER.debug("Invalid response length for handle status read: %d", len(response))
                return None

            status = response[5]
            _LOGGER.debug("Handle status read: 0x%02X", status)
            return status
        except Exception as e:
            _LOGGER.error("Error reading handle status: %s", e)
            return None

    async def reset(self) -> Optional[bytes]:
        """Reset the device."""
        _LOGGER.debug("Sending reset command")
        rs485_command = bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_RESET])
        return await self._send_command_with_retry(rs485_command)

    async def delete(self) -> Optional[bytes]:
        """Delete the device configuration."""
        _LOGGER.debug("Sending delete command")
        rs485_command = bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_DELETE])
        return await self._send_command_with_retry(rs485_command)

    async def read_all_status(self) -> dict:
        """Read all status information in one call (more efficient for polling)."""
        result = {
            "position": None,
            "motor_status": None,
            "active_switch": None,
            "passive_switch": None,
            "handle_status": None,
        }

        # Read position first (most important)
        result["position"] = await self.read_cover_position()
        
        # Read other status values
        result["motor_status"] = await self.read_motor_status()
        result["active_switch"], result["passive_switch"] = await self.read_switch_status()
        result["handle_status"] = await self.read_handle_status()

        return result

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
            new_id_h,
        )

        # Validate address bytes
        if new_id_l in (0x00, 0xFF) or new_id_h in (0x00, 0xFF):
            _LOGGER.error("Invalid address bytes. Cannot be 0x00 or 0xFF")
            return False

        try:
            async with self._lock:
                if not await self.ensure_connected():
                    _LOGGER.error("Failed to establish connection for address programming")
                    return False

                # Wait for slave request (0x04) after button press
                # Default address (0xFEFE) + Function (0x04) + Data addr (0x01)
                expected_request = bytes([START_CODE, 0xFE, 0xFE, DEVICE_ADDRESS_SLAVE_REQUEST, 0x01])

                # Listen for the request for up to 10 seconds
                start_time = asyncio.get_event_loop().time()
                while (asyncio.get_event_loop().time() - start_time) < 10:
                    try:
                        response = await asyncio.wait_for(self._reader.read(1024), timeout=1.0)
                        if response and response.startswith(expected_request):
                            _LOGGER.debug("Received slave programming request")
                            break
                    except asyncio.TimeoutError:
                        continue
                else:
                    _LOGGER.error("Timeout waiting for slave programming request")
                    return False

                # Send write address command
                command = bytes(
                    [
                        START_CODE,
                        0x00,
                        0x00,  # Use 0x0000 when programming
                        DEVICE_ADDRESS_WRITE,
                        DEVICE_ADDRESS_DATA_ADDR,
                        DEVICE_ADDRESS_DATA_LENGTH,
                        new_id_l,
                        new_id_h,
                    ]
                )

                # Add CRC
                crc = self.calculate_crc(command)
                command += crc

                _LOGGER.debug(
                    "Sending address programming command: %s",
                    binascii.hexlify(command).decode(),
                )

                self._writer.write(command)
                await asyncio.wait_for(self._writer.drain(), timeout=COMMAND_TIMEOUT)

                # Wait for confirmation response
                try:
                    response = await asyncio.wait_for(self._reader.read(1024), timeout=5.0)
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

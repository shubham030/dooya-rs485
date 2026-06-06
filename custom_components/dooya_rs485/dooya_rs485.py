"""API for controlling Dooya curtain motor."""
import asyncio
import binascii
import logging
from typing import Optional

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
    CURTAIN_COMMAND_TOGGLE,
    CURTAIN_READ_WRITE_PERCENT,
    CURTAIN_READ_WRITE_DIRECTION,
    CURTAIN_READ_WRITE_MANUAL_ENABLE,
    CURTAIN_READ_WRITE_MOTOR_STATUS,
    CURTAIN_READ_WRITE_SWITCH_PASSIVE,
    CURTAIN_READ_WRITE_SWITCH_ACTIVE,
    CURTAIN_READ_WRITE_SOFTWARE_VERSION,
    CURTAIN_READ_WRITE_PROTOCOL_VERSION,
    POSITION_NO_STROKE,
    POSITION_MAX,
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

# Read responses are framed as:
#   [0] start  [1] id_l  [2] id_h  [3] function  [4] data length  [5..] data  [-2:] CRC
DATA_OFFSET = 5  # Index of the first data byte in a read response


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
        """Set the cover position (0-100)."""
        _LOGGER.debug("Setting cover position to %d%%", position)
        rs485_command = bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_PERCENT, position])
        return await self._send_command_with_retry(rs485_command)

    async def toggle(self) -> Optional[bytes]:
        """Toggle the curtain using the motor's native negate command.

        The motor opens if the last command was close, otherwise it closes.
        """
        _LOGGER.debug("Sending toggle (negate) command")
        rs485_command = bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_TOGGLE])
        return await self._send_command_with_retry(rs485_command)

    async def _read_register(self, register: int) -> Optional[int]:
        """Read a single register and return its data byte, or None on failure."""
        rs485_command = bytes([CURTAIN_READ, register, 0x01])
        response = await self._send_command_with_retry(rs485_command)

        if response is None:
            _LOGGER.debug("No response for read of register 0x%02X", register)
            return None

        # A valid read response is at least 6 bytes (header + length + data, plus CRC).
        if len(response) <= DATA_OFFSET:
            _LOGGER.debug(
                "Read response for register 0x%02X too short: %d bytes",
                register,
                len(response),
            )
            return None

        return response[DATA_OFFSET]

    async def read_cover_position(self) -> Optional[int]:
        """Read the cover position (0-100), or None if unknown/stroke not set."""
        position = await self._read_register(CURTAIN_READ_WRITE_PERCENT)
        if position is None:
            return None

        _LOGGER.debug("Raw position from device: 0x%02X", position)

        if position == POSITION_NO_STROKE:
            _LOGGER.warning("Device reports stroke is not set")
            return None

        if position > POSITION_MAX:
            _LOGGER.debug("Invalid position value received: 0x%02X", position)
            return None

        _LOGGER.debug("Cover position read: %d%%", position)
        return position

    async def read_motor_status(self) -> Optional[int]:
        """Read the motor status (see MOTOR_STATUS_* constants)."""
        return await self._read_register(CURTAIN_READ_WRITE_MOTOR_STATUS)

    async def write_register(self, register: int, value: int) -> bool:
        """Write a single-byte configuration register.

        Returns True if the device returned a valid (framed, CRC-checked) ack.
        """
        rs485_command = bytes([CURTAIN_WRITE, register, 0x01, value])
        response = await self._send_command_with_retry(rs485_command)
        if response is None:
            _LOGGER.warning("No ack writing 0x%02X to register 0x%02X", value, register)
            return False
        return True

    async def read_direction(self) -> Optional[int]:
        """Read the motor default direction (config)."""
        return await self._read_register(CURTAIN_READ_WRITE_DIRECTION)

    async def read_manual_enable(self) -> Optional[int]:
        """Read the manual (hand-pull) start enable setting (config)."""
        return await self._read_register(CURTAIN_READ_WRITE_MANUAL_ENABLE)

    async def read_switch_type_passive(self) -> Optional[int]:
        """Read the passive (weak current) external switch type (config)."""
        return await self._read_register(CURTAIN_READ_WRITE_SWITCH_PASSIVE)

    async def read_switch_type_active(self) -> Optional[int]:
        """Read the active (high current) external switch type (config)."""
        return await self._read_register(CURTAIN_READ_WRITE_SWITCH_ACTIVE)

    async def read_software_version(self) -> Optional[int]:
        """Read the software/firmware version (register 0xFD, 0-255)."""
        return await self._read_register(CURTAIN_READ_WRITE_SOFTWARE_VERSION)

    async def read_protocol_version(self) -> Optional[int]:
        """Read the protocol version (register 0xFE, fixed e.g. 0xA4)."""
        return await self._read_register(CURTAIN_READ_WRITE_PROTOCOL_VERSION)

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

            return self._validate_response(response)

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

    def _validate_response(self, response: bytes) -> Optional[bytes]:
        """Validate framing, source address and CRC of a device response."""
        # Minimum useful response is a full frame: start + addr(2) + fn + crc(2).
        if len(response) < 6:
            _LOGGER.debug("Response too short: %d bytes", len(response))
            return None

        # Validate start byte.
        if response[0] != START_CODE:
            _LOGGER.warning("Unexpected start byte: 0x%02X", response[0])
            return None

        # Validate the frame came from the device we addressed. On a multi-drop
        # RS485 bus this guards against cross-talk from other motors.
        if response[1] != self.device_id_l or response[2] != self.device_id_h:
            _LOGGER.warning(
                "Response from unexpected device 0x%02X%02X (expected 0x%02X%02X)",
                response[2],
                response[1],
                self.device_id_h,
                self.device_id_l,
            )
            return None

        # Validate CRC (last two bytes, little-endian).
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

    def calculate_crc(self, data: bytes) -> bytes:
        """Calculate CRC16 Modbus (little-endian byte order)."""
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

    async def read_status(self) -> dict:
        """Read the runtime status used for polling.

        Returns ``position`` (0-100 or None), ``motor_status`` and ``stroke_set``
        (True/False when known, None when the position could not be read).
        """
        raw_position = await self._read_register(CURTAIN_READ_WRITE_PERCENT)
        motor_status = await self.read_motor_status()

        position: Optional[int] = None
        stroke_set: Optional[bool] = None
        if raw_position is not None:
            if raw_position == POSITION_NO_STROKE:
                stroke_set = False
                _LOGGER.warning("Device reports stroke is not set")
            elif raw_position <= POSITION_MAX:
                position = raw_position
                stroke_set = True
            else:
                _LOGGER.debug("Invalid position value received: 0x%02X", raw_position)

        return {
            "position": position,
            "motor_status": motor_status,
            "stroke_set": stroke_set,
        }

    async def read_device_attributes(self) -> dict:
        """Read static device configuration/identity (read once at setup)."""
        return {
            "direction": await self.read_direction(),
            "manual_enable": await self.read_manual_enable(),
            "switch_type_passive": await self.read_switch_type_passive(),
            "switch_type_active": await self.read_switch_type_active(),
            "software_version": await self.read_software_version(),
            "protocol_version": await self.read_protocol_version(),
        }

    async def reset(self) -> Optional[bytes]:
        """Restore the device to factory settings (also clears the stroke)."""
        _LOGGER.debug("Sending reset command")
        rs485_command = bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_RESET])
        return await self._send_command_with_retry(rs485_command)

    async def delete(self) -> Optional[bytes]:
        """Delete the device trip/stroke configuration."""
        _LOGGER.debug("Sending delete command")
        rs485_command = bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_DELETE])
        return await self._send_command_with_retry(rs485_command)

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

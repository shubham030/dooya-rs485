"""API for controlling Dooya curtain motor."""
import socket
import binascii

from const import *

class DooyaController:
    """Class to control Dooya curtain motor."""

    def __init__(self, tcp_port, tcp_address, device_id_l, device_id_h):
        """Initialize the controller."""
        self.tcp_port = tcp_port
        self.tcp_address = tcp_address
        self.device_id_l = device_id_l
        self.device_id_h = device_id_h
        # Initialize serial connection
        self.serial = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Connect to the TCP server
        try:
            self.serial.connect((self.tcp_address, self.tcp_port))
        except socket.error as e:
            _LOGGER.error(f"Failed to connect to {self.tcp_address}:{self.tcp_port} - {e}")
            raise


    async def open(self):
        """Open the curtain."""
        rs485_command = bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_OPEN])
        response = await self.send_rs485_command(rs485_command)
        return response

    async def close(self):
        """Close the curtain."""
        rs485_command = bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_CLOSE])
        response = await self.send_rs485_command(rs485_command)
        return response

    async def stop(self):
        """Stop the curtain."""
        rs485_command = bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_STOP])
        response = await self.send_rs485_command(rs485_command)
        return response
    
    async def set_cover_position(self, position):
        """Set the cover position."""
        rs485_command = bytes([CURTAIN_COMMAND, CURTAIN_COMMAND_PERCENT, position])
        response = await self.send_rs485_command(rs485_command)
        return response

    async def read_cover_position(self):
        """Read the cover position."""
        rs485_command = bytes([CURTAIN_READ,CURTAIN_READ_WRITE_PERCENT,0x01])
        response = await self.send_rs485_command(rs485_command)
        # 5th byte contains the cover position, 0-100, FF if position is unknown
        return response[5]

    async def read_cover_direction(self):
        """Read the cover direction."""
        rs485_command = bytes([CURTAIN_READ,CURTAIN_READ_WRITE_DIRECTION,0x01])
        response = await self.send_rs485_command(rs485_command)
        return response[5]

    async def send_rs485_command(self, rs485_command):
        """Send RS485 command over TCP."""
        # Construct full command
        full_command = bytes([START_CODE, self.device_id_l, self.device_id_h]) + rs485_command
        # Append CRC to RS485 command
        crc = self.calculate_crc(full_command)
        full_command += crc

        try:
            # Send the full command
            self.serial.sendall(full_command)

            # Receive response (if any)
            response = self.serial.recv(1024)
            print("Response received:", binascii.hexlify(response).decode())
            return response
                
        except ConnectionRefusedError:
            print("Connection refused. Make sure the server is running and the address and port are correct.")
            return None
        except Exception as e:
            print("An error occurred:", e)
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
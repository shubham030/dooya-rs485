"""Constants for the Dooya RS485 integration.

This module is intentionally free of Home Assistant imports so the protocol
layer (``dooya_rs485.py``) can be imported and unit-tested standalone.
"""

DOMAIN = "dooya_rs485"
VERSION = "1.1.0"

# RS485 Protocol Constants
START_CODE = 0x55  # Start byte for all commands

# Command Types
CURTAIN_READ = 0x01   # Read register command
CURTAIN_WRITE = 0x02  # Write register command
CURTAIN_COMMAND = 0x03  # Control command

# Commands (control command 0x03 data address)
CURTAIN_COMMAND_OPEN = 0x01      # Open curtain command
CURTAIN_COMMAND_CLOSE = 0x02     # Close curtain command
CURTAIN_COMMAND_STOP = 0x03      # Stop curtain command
CURTAIN_COMMAND_PERCENT = 0x04   # Set position command
CURTAIN_COMMAND_DELETE = 0x07    # Delete trip (stroke) command
CURTAIN_COMMAND_RESET = 0x08     # Restore factory settings command

# Read/Write Registers (data addresses)
CURTAIN_READ_WRITE_ADDR_LOW = 0x00       # Device address low byte
CURTAIN_READ_WRITE_ADDR_HIGH = 0x01      # Device address high byte
CURTAIN_READ_WRITE_PERCENT = 0x02        # Current position (0x00-0x64, 0xFF = no stroke)
CURTAIN_READ_WRITE_DIRECTION = 0x03      # Motor default direction (config)
CURTAIN_READ_WRITE_MANUAL_ENABLE = 0x04  # Manual (hand-pull) start enable (config)
CURTAIN_READ_WRITE_MOTOR_STATUS = 0x05   # Motor status (runtime)
CURTAIN_READ_WRITE_SWITCH_PASSIVE = 0x27  # Passive (weak current) switch type (config)
CURTAIN_READ_WRITE_SWITCH_ACTIVE = 0x28   # Active (high current) switch type (config)
CURTAIN_READ_WRITE_SOFTWARE_VERSION = 0xFD  # Software/firmware version (0-255)
CURTAIN_READ_WRITE_PROTOCOL_VERSION = 0xFE  # Protocol version (fixed, e.g. 0xA4)

# Motor status values (register 0x05) -- per protocol spec section 0x05.
# NOTE: the protocol has NO "error" status. 0x02 means the motor is running
# in the close direction, not a fault.
MOTOR_STATUS_STOPPED = 0x00  # Motor stopped
MOTOR_STATUS_OPENING = 0x01  # Motor running toward open
MOTOR_STATUS_CLOSING = 0x02  # Motor running toward close
MOTOR_STATUS_SETTING = 0x03  # Motor in setting/calibration mode

# Motor default direction (register 0x03, config)
DIRECTION_DEFAULT = 0x00
DIRECTION_REVERSED = 0x01

# Manual (hand-pull) start enable (register 0x04, config)
MANUAL_ENABLE_ON = 0x00   # Can be started by hand (default)
MANUAL_ENABLE_OFF = 0x01  # Hand-pull start disabled

# Passive (weak current) switch type (register 0x27, config)
SWITCH_PASSIVE_TYPES = {
    0x01: "double_bounce",
    0x02: "non_bounce",
    0x03: "dc246_electronic",
    0x04: "single_key_cycle",
}

# Active (high current) switch type (register 0x28, config)
SWITCH_ACTIVE_TYPES = {
    0x00: "double_key_non_rebound",
    0x01: "hotel_mode",
    0x02: "double_key_rebound",
}

# Position sentinels
POSITION_NO_STROKE = 0xFF  # Returned when no stroke (travel limits) is set
POSITION_MAX = 0x64        # 100% (fully open)

# Device Address Programming
DEVICE_ADDRESS_SLAVE_REQUEST = 0x04  # Slave request command for address programming
DEVICE_ADDRESS_WRITE = 0x02          # Write address command
DEVICE_ADDRESS_DATA_ADDR = 0x00      # Data address for device address
DEVICE_ADDRESS_DATA_LENGTH = 0x02    # Data length for address (2 bytes)

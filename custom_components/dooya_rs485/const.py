"""Constants for the Dooya RS485 integration."""
from homeassistant.components.cover import CoverEntityFeature

DOMAIN = "dooya_rs485"

# Custom States
STATE_ERROR = "error"  # State when the device reports an error condition

# RS485 Protocol Constants
START_CODE = 0x55  # Start byte for all commands

# Command Types
CURTAIN_READ = 0x01   # Read register command
CURTAIN_WRITE = 0x02  # Write register command
CURTAIN_COMMAND = 0x03  # Control command

# Commands
CURTAIN_COMMAND_OPEN = 0x01      # Open curtain command
CURTAIN_COMMAND_CLOSE = 0x02     # Close curtain command
CURTAIN_COMMAND_STOP = 0x03      # Stop curtain command
CURTAIN_COMMAND_PERCENT = 0x04   # Set position command
CURTAIN_COMMAND_DELETE = 0x07    # Delete device command
CURTAIN_COMMAND_RESET = 0x08     # Reset device command

# Read/Write Registers
CURTAIN_READ_WRITE_ADDR_LOW = 0x00      # Device address low byte
CURTAIN_READ_WRITE_ADDR_HIGH = 0x01     # Device address high byte
CURTAIN_READ_WRITE_ADDR = 0x00          # Device address (combined)
CURTAIN_READ_WRITE_PERCENT = 0x02       # Current position (0-100%)
CURTAIN_READ_WRITE_DIRECTION = 0x03     # Movement direction
CURTAIN_READ_WRITE_HANDLE = 0x04        # Handle status
CURTAIN_READ_WRITE_MOTOR_STATUS = 0x05  # Motor status
CURTAIN_READ_WRITE_SWITCH_PASSIVE = 0x27 # Passive switch status
CURTAIN_READ_WRITE_SWITCH_ACTIVE = 0x28  # Active switch status
CURTAIN_READ_WRITE_VERSION = 0xFE        # Device version

# Status Codes
MOTOR_STATUS_STOPPED = 0x00  # Motor is stopped
MOTOR_STATUS_RUNNING = 0x01  # Motor is running
MOTOR_STATUS_ERROR = 0x02    # Motor has reported an error

SWITCH_STATUS_NORMAL = 0x00     # Switch is in normal position
SWITCH_STATUS_TRIGGERED = 0x01  # Switch has been triggered

HANDLE_STATUS_NORMAL = 0x00     # Handle is in normal position
HANDLE_STATUS_OPERATED = 0x01   # Handle has been operated

# Cover Features
SUPPORTED_FEATURES = (
    CoverEntityFeature.OPEN |
    CoverEntityFeature.CLOSE |
    CoverEntityFeature.STOP
)

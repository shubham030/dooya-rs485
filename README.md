# Dooya RS485 Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

A Home Assistant integration for controlling Dooya curtain motors via RS485 (through a TCP gateway).

## Features

- Control Dooya curtain motors (open, close, stop)
- Set specific positions (0-100%)
- Read motor status and position
- Monitor switch and handle status
- Program device addresses
- Support for multiple curtains
- Automatic error recovery

## Prerequisites

- Home Assistant
- RS485 to TCP gateway (configured and connected to your network)
- Dooya curtain motor with RS485 support

## Installation

### HACS (Recommended)

1. Add this repository as a custom repository in HACS:
    - Click on HACS in the sidebar
    - Click on "Integrations"
    - Click the three dots in the top right corner
    - Select "Custom repositories"
    - Add `https://github.com/shubham030/dooya-rs485` as a new repository
    - Category: Integration

2. Click "Install" on the Dooya RS485 integration

### Manual Installation

1. Download the latest release from the [releases page](https://github.com/shubham030/dooya-rs485/releases)
2. Extract the `custom_components/dooya_rs485` folder to your Home Assistant's `custom_components` directory
3. Restart Home Assistant

## Configuration

1. Go to Home Assistant Settings > Devices & Services
2. Click "Add Integration"
3. Search for "Dooya RS485"
4. Fill in the required information:
   - Name: A friendly name for your curtain
   - TCP Address: IP address of your RS485 gateway
   - TCP Port: Port number of your RS485 gateway
   - Device ID Low: Low byte of the device address (0-255 or hex 0x00-0xFF)
   - Device ID High: High byte of the device address (0-255 or hex 0x00-0xFF)

## Device Address Programming

The integration supports programming new device addresses. To change a device's address:

1. Press and hold the motor setting button for 5 seconds until the LED flashes twice
2. Within 10 seconds, call the `dooya_rs485.program_address` service:

```yaml
service: dooya_rs485.program_address
target:
  entity_id: cover.your_cover_name
data:
  address_low: 18   # New low byte (1-254)
  address_high: 52  # New high byte (1-254)
```

**Important Notes:**
- Address bytes cannot be 0x00 or 0xFF
- Default factory address is 0xFEFE
- LED will flash 5 times to confirm successful programming
- If programming fails, the device keeps its previous address

## Services

### program_address
Program a new device address.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| address_low | int | Yes | Low byte of new address (1-254) |
| address_high | int | Yes | High byte of new address (1-254) |

### open_cover
Open the curtain fully.

### close_cover
Close the curtain fully.

### stop_cover
Stop the curtain at its current position.

### set_cover_position
Move the curtain to a specific position.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| position | int | Yes | Target position (0-100) |

## Attributes

The integration exposes several attributes for monitoring device status:

| Attribute | Description |
|-----------|-------------|
| current_position | Current position (0-100%) |
| motor_status | Motor status (stopped/running/error) |
| active_switch_status | Active switch status |
| passive_switch_status | Passive switch status |
| handle_status | Handle operation status |
| device_version | Device firmware version |

## Protocol Details

The integration uses the Dooya RS485 protocol with the following specifications:

- Start Code: 0x55
- Command Types:
  - Read (0x01)
  - Write (0x02)
  - Control (0x03)
  - Address Programming (0x04)
- CRC16 checksum for all commands
- Default factory address: 0xFEFE

## Troubleshooting

1. **Connection Issues**
   - Verify TCP gateway IP address and port
   - Check physical RS485 connections
   - Ensure correct device address is configured

2. **Communication Errors**
   - Integration will automatically retry failed commands
   - After 3 consecutive failures, device will attempt reset
   - Check logs for detailed error messages

3. **Address Programming Fails**
   - Ensure button is held until LED flashes twice
   - Program address within 10 seconds of LED signal
   - Verify new address bytes are not 0x00 or 0xFF

## Support

For bugs, feature requests, or support:
- [Open an issue](https://github.com/shubham030/dooya-rs485/issues)
- [View source code](https://github.com/shubham030/dooya-rs485)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Credits

Created and maintained by [@shubham030](https://github.com/shubham030)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

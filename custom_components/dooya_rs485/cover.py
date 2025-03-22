"""Cover platform for Dooya RS485 integration."""
import logging
from typing import Any

from homeassistant.components.cover import CoverEntity, CoverEntityFeature, CoverDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import (
    STATE_CLOSED,
    STATE_CLOSING,
    STATE_OPENING,
    STATE_OPEN,
    STATE_UNKNOWN,
)

from .const import DOMAIN, SUPPORTED_FEATURES, STATE_ERROR

_LOGGER = logging.getLogger(__name__)

# Motor Status Constants
MOTOR_STATUS_STOPPED = 0x00
MOTOR_STATUS_RUNNING = 0x01
MOTOR_STATUS_ERROR = 0x02

# Switch Status Constants
SWITCH_STATUS_NORMAL = 0x00
SWITCH_STATUS_TRIGGERED = 0x01

# Handle Status Constants
HANDLE_STATUS_NORMAL = 0x00
HANDLE_STATUS_OPERATED = 0x01

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dooya RS485 cover from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    _LOGGER.info("Setting up cover entity with name: %s", data["data"]["name"])
    async_add_entities([DooyaCover(data["controller"], data["data"]["name"])])


class DooyaCover(CoverEntity):
    """Representation of a Dooya RS485 cover."""

    def __init__(self, controller, name: str) -> None:
        """Initialize the cover."""
        _LOGGER.info("Initializing DooyaCover with name: %s", name)
        self._name = name
        self._state = STATE_UNKNOWN
        self._controller = controller
        self._attr_unique_id = f"dooya_{name.lower().replace(' ', '_')}"
        self._attr_device_class = CoverDeviceClass.CURTAIN
        self._last_position = None
        self._current_position = None
        self._target_position = None
        self._motor_status = None
        self._active_switch_status = None
        self._passive_switch_status = None
        self._handle_status = None
        self._device_version = None
        self._error_count = 0
        self._max_errors = 3
        _LOGGER.info("Cover entity initialized with name: %s, unique_id: %s", self._name, self._attr_unique_id)

    @property
    def name(self) -> str:
        """Return the name of the cover."""
        return self._name

    @property
    def state(self) -> str:
        """Return the state of the cover."""
        if self._motor_status == MOTOR_STATUS_ERROR:
            return STATE_ERROR
        return self._state

    @property
    def current_cover_position(self) -> int | None:
        """Return current position of cover."""
        return self._current_position

    @property
    def supported_features(self) -> CoverEntityFeature:
        """Flag supported features."""
        return SUPPORTED_FEATURES | CoverEntityFeature.SET_POSITION

    @property
    def is_closed(self) -> bool:
        """Return if the cover is closed."""
        return self._state == STATE_CLOSED

    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening."""
        return self._state == STATE_OPENING

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing."""
        return self._state == STATE_CLOSING

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "motor_status": self._motor_status,
            "active_switch_status": self._active_switch_status,
            "passive_switch_status": self._passive_switch_status,
            "handle_status": self._handle_status,
            "device_version": self._device_version,
        }

    def _normalize_position(self, position: int) -> int:
        """Normalize position value to 0-100 range."""
        if position is None:
            return None
        # Position from device is already in 0-100 range (0x00-0x64)
        return position

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        try:
            await self._controller.open()
            self._state = STATE_OPENING
            self._target_position = 100
            self._error_count = 0
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Error opening cover: %s", err)
            self._state = STATE_UNKNOWN
            self._target_position = None
            self._error_count += 1
            self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        try:
            await self._controller.close()
            self._state = STATE_CLOSING
            self._target_position = 0
            self._error_count = 0
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Error closing cover: %s", err)
            self._state = STATE_UNKNOWN
            self._target_position = None
            self._error_count += 1
            self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        try:
            await self._controller.stop()
            self._target_position = None
            self._error_count = 0
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Error stopping cover: %s", err)
            self._state = STATE_UNKNOWN
            self._target_position = None
            self._error_count += 1
            self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        try:
            position = kwargs.get("position")
            if position is not None:
                position = self._normalize_position(position)
                _LOGGER.info("Setting cover position to %d%%", position)
                await self._controller.set_cover_position(position)
                self._target_position = position
                self._state = STATE_OPENING if position > self._current_position else STATE_CLOSING
                self._error_count = 0
                self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Error setting cover position: %s", err)
            self._state = STATE_UNKNOWN
            self._target_position = None
            self._error_count += 1
            self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the cover state."""
        try:
            # Read all status information
            pos = await self._controller.read_cover_position()
            motor_status = await self._controller.read_motor_status()
            active_switch, passive_switch = await self._controller.read_switch_status()
            handle_status = await self._controller.read_handle_status()
            
            # Update device status
            self._motor_status = motor_status
            self._active_switch_status = active_switch
            self._passive_switch_status = passive_switch
            self._handle_status = handle_status
            
            # Handle motor error status
            if motor_status == MOTOR_STATUS_ERROR:
                _LOGGER.error("Motor reported error status")
                self._state = STATE_ERROR
                self._current_position = None
                self._target_position = None
                return
                
            # Handle switch status
            if active_switch == SWITCH_STATUS_TRIGGERED or passive_switch == SWITCH_STATUS_TRIGGERED:
                _LOGGER.warning("Switch triggered - Active: %s, Passive: %s", active_switch, passive_switch)
            
            # Handle handle status
            if handle_status == HANDLE_STATUS_OPERATED:
                _LOGGER.info("Handle was operated")
            
            # Handle position updates
            if pos is None:
                self._state = STATE_UNKNOWN
                self._current_position = None
                self._target_position = None
            elif pos == 0:
                self._state = STATE_CLOSED
                self._current_position = 0
                self._target_position = None
            elif pos == 100:
                self._state = STATE_OPEN
                self._current_position = 100
                self._target_position = None
            else:
                self._current_position = pos
                if self._target_position is not None:
                    if abs(pos - self._target_position) <= 5:  # 5% tolerance
                        self._state = STATE_OPEN if pos > 50 else STATE_CLOSED
                        self._target_position = None
                    else:
                        self._state = STATE_OPENING if pos < self._target_position else STATE_CLOSING
                elif self._last_position is not None:
                    if pos > self._last_position:
                        self._state = STATE_OPENING
                    elif pos < self._last_position:
                        self._state = STATE_CLOSING
                    else:
                        self._state = STATE_OPEN if pos > 50 else STATE_CLOSED
                else:
                    self._state = STATE_OPEN if pos > 50 else STATE_CLOSED
            
            self._last_position = pos
            self._error_count = 0
            self.async_write_ha_state()
            
        except Exception as err:
            _LOGGER.error("Error updating cover state: %s", err)
            self._state = STATE_UNKNOWN
            self._current_position = None
            self._target_position = None
            self._error_count += 1
            self.async_write_ha_state()
            
            # If we've exceeded max errors, try to reset the device
            if self._error_count >= self._max_errors:
                _LOGGER.warning("Max errors reached, attempting device reset")
                try:
                    await self._controller.reset()
                    self._error_count = 0
                except Exception as reset_err:
                    _LOGGER.error("Error resetting device: %s", reset_err)

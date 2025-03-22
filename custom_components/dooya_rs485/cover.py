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

from .const import DOMAIN, SUPPORTED_FEATURES

_LOGGER = logging.getLogger(__name__)

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
        _LOGGER.info("Cover entity initialized with name: %s, unique_id: %s", self._name, self._attr_unique_id)

    @property
    def name(self) -> str:
        """Return the name of the cover."""
        return self._name

    @property
    def state(self) -> str:
        """Return the state of the cover."""
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

    def _normalize_position(self, position: int) -> int:
        """Normalize position value to 0-100 range."""
        if position is None or position == 255:
            return None
        # Ensure position is between 0 and 100
        return max(0, min(100, position))

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        try:
            await self._controller.open()
            self._state = STATE_OPENING
            self._target_position = 100
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Error opening cover: %s", err)
            self._state = STATE_UNKNOWN
            self._target_position = None
            self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        try:
            await self._controller.close()
            self._state = STATE_CLOSING
            self._target_position = 0
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Error closing cover: %s", err)
            self._state = STATE_UNKNOWN
            self._target_position = None
            self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        try:
            await self._controller.stop()
            self._target_position = None
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Error stopping cover: %s", err)
            self._state = STATE_UNKNOWN
            self._target_position = None
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
                self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Error setting cover position: %s", err)
            self._state = STATE_UNKNOWN
            self._target_position = None
            self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the cover state."""
        try:
            pos = await self._controller.read_cover_position()
            _LOGGER.debug("Raw position from device: %d", pos)
            
            # Normalize position to 0-100 range
            normalized_pos = self._normalize_position(pos)
            _LOGGER.debug("Normalized position: %d", normalized_pos)
            
            # Handle invalid position values
            if normalized_pos is None:
                self._state = STATE_UNKNOWN
                self._current_position = None
                self._target_position = None
            # Handle known positions
            elif normalized_pos == 0:
                self._state = STATE_CLOSED
                self._current_position = 0
                self._target_position = None
            elif normalized_pos == 100:
                self._state = STATE_OPEN
                self._current_position = 100
                self._target_position = None
            # Handle intermediate positions
            else:
                self._current_position = normalized_pos
                # If we have a target position, check if we've reached it
                if self._target_position is not None:
                    if abs(normalized_pos - self._target_position) <= 5:  # 5% tolerance
                        self._state = STATE_OPEN if normalized_pos > 50 else STATE_CLOSED
                        self._target_position = None
                    else:
                        self._state = STATE_OPENING if normalized_pos < self._target_position else STATE_CLOSING
                # If no target position, determine state based on last position
                elif self._last_position is not None:
                    if normalized_pos > self._last_position:
                        self._state = STATE_OPENING
                    elif normalized_pos < self._last_position:
                        self._state = STATE_CLOSING
                    else:
                        # Position hasn't changed, determine final state based on position
                        if normalized_pos > 50:
                            self._state = STATE_OPEN
                        else:
                            self._state = STATE_CLOSED
                else:
                    # No last position, assume current position is final
                    if normalized_pos > 50:
                        self._state = STATE_OPEN
                    else:
                        self._state = STATE_CLOSED
            
            self._last_position = normalized_pos
            self.async_write_ha_state()
            
        except Exception as err:
            _LOGGER.error("Error updating cover state: %s", err)
            self._state = STATE_UNKNOWN
            self._current_position = None
            self._target_position = None
            self.async_write_ha_state()

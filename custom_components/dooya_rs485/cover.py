"""Cover platform for Dooya RS485 integration."""
import logging
from typing import Any

from homeassistant.components.cover import CoverEntity, CoverEntityFeature
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
    async_add_entities([DooyaCover(data["controller"], data["data"]["name"])])


class DooyaCover(CoverEntity):
    """Representation of a Dooya RS485 cover."""

    def __init__(self, controller, name: str) -> None:
        """Initialize the cover."""
        self._name = name
        self._state = STATE_UNKNOWN
        self._controller = controller
        self._attr_unique_id = f"dooya_{name.lower().replace(' ', '_')}"

    @property
    def name(self) -> str:
        """Return the name of the cover."""
        return self._name

    @property
    def state(self) -> str:
        """Return the state of the cover."""
        return self._state

    @property
    def supported_features(self) -> CoverEntityFeature:
        """Flag supported features."""
        return SUPPORTED_FEATURES

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

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        try:
            await self._controller.open()
            self._state = STATE_OPENING
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Error opening cover: %s", err)
            self._state = STATE_UNKNOWN
            self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        try:
            await self._controller.close()
            self._state = STATE_CLOSING
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Error closing cover: %s", err)
            self._state = STATE_UNKNOWN
            self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        try:
            await self._controller.stop()
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Error stopping cover: %s", err)
            self._state = STATE_UNKNOWN
            self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the cover state."""
        try:
            pos = await self._controller.read_cover_position()
            if pos == 255:
                self._state = STATE_UNKNOWN
            elif pos == 0:
                self._state = STATE_CLOSED
            else:
                self._state = STATE_OPEN
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Error updating cover state: %s", err)
            self._state = STATE_UNKNOWN
            self.async_write_ha_state()

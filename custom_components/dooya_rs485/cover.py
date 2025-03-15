"""Support for controlling Dooya curtain motor."""
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
import logging

from homeassistant.components.cover import (
    CoverEntity,
    SUPPORT_OPEN,
    SUPPORT_CLOSE,
    SUPPORT_STOP,
    PLATFORM_SCHEMA,
)
from homeassistant.const import STATE_CLOSED, STATE_CLOSING, STATE_OPENING, STATE_OPEN


from .const import DOMAIN
from .dooya_motor import DooyaController

def validate_device_id(value):
    """Validate that the value is a valid device ID (integer between 0 and 255)."""
    if not isinstance(value, int):
        raise vol.Invalid("Invalid value. Must be an integer.")
    if value < 0 or value > 255:
        raise vol.Invalid("Invalid value. Must be between 0 and 255.")
    return value

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
        vol.Required("platform"): "dooya_motor",
        vol.Required("tcp_port"): cv.port,
        vol.Required("tcp_address"): cv.string,
        vol.Required("device_id_l"): validate_device_id,
        vol.Required("device_id_h"): validate_device_id,
    })

_LOGGER = logging.getLogger(__name__)

async def setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Dooya cover platform."""
    _LOGGER.error(config)
    async_add_entities([DooyaCover(config)])


class DooyaCover(CoverEntity):
    """Representation of a Dooya cover."""

    def __init__(self, config):
        """Initialize the cover."""
        self._name = "Dooya Curtain"
        self._state = STATE_OPEN
        self._controller = DooyaController(
            tcp_port=config["tcp_port"],
            tcp_address=config["tcp_address"],
            device_id_l=config["device_id_l"],
            device_id_h=config["device_id_h"],
        )

    @property
    def name(self):
        """Return the name of the cover."""
        return self._name

    @property
    def state(self):
        """Return the state of the cover."""
        return self._state

    @property
    def supported_features(self):
        """Flag supported features."""
        return SUPPORT_OPEN | SUPPORT_CLOSE | SUPPORT_STOP

    @property
    async def is_closed(self):
        """Return if the cover is closed."""
        return self._state == STATE_CLOSED


    @property
    def is_opening(self):
        """Return if the cover is opening."""
        return self._state == STATE_OPENING

    @property
    def is_closing(self):
        """Return if the cover is closing."""
        return self._state == STATE_CLOSING

    async def async_open_cover(self, **kwargs):
        """Open the cover."""
        await self._controller.open()
        self._state = STATE_OPEN

    async def async_close_cover(self, **kwargs):
        """Close the cover."""
        await self._controller.close()
        self._state = STATE_CLOSED

    async def async_stop_cover(self, **kwargs):
        """Stop the cover."""
        await self._controller.stop()

    async def async_update(self):
        """Update the cover state."""
        pos = await self._controller.read_cover_position()
        if pos == 255:
            self._state = None
        elif pos == 0:
            self._state = STATE_CLOSED
        else:
            self._state = STATE_OPEN

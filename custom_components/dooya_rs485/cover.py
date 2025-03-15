import logging
from homeassistant.components.cover import CoverEntity, CoverEntityFeature
from homeassistant.const import STATE_CLOSED, STATE_CLOSING, STATE_OPENING, STATE_OPEN
from .const import DOMAIN
from .dooya_rs485 import DooyaController

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Dooya curtain cover from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DooyaCover(data)])


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
        return CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP

    @property
    def is_closed(self):
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
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs):
        """Close the cover."""
        await self._controller.close()
        self._state = STATE_CLOSED
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs):
        """Stop the cover."""
        await self._controller.stop()
        self.async_write_ha_state()

    async def async_update(self):
        """Update the cover state."""
        pos = await self._controller.read_cover_position()
        if pos == 255:
            self._state = None
        elif pos == 0:
            self._state = STATE_CLOSED
        else:
            self._state = STATE_OPEN

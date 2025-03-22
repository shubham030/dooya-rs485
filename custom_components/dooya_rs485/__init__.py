"""The Dooya RS485 integration."""
import logging
from typing import Any

from homeassistant import config_entries, core
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .dooya_rs485 import DooyaController

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Dooya RS485 integration."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Dooya RS485 from a config entry."""
    try:
        controller = DooyaController(
            tcp_port=entry.data["tcp_port"],
            tcp_address=entry.data["tcp_address"],
            device_id_l=entry.data["device_id_l"],
            device_id_h=entry.data["device_id_h"],
        )
        hass.data[DOMAIN][entry.entry_id] = {
            "data": entry.data,
            "controller": controller
        }
        await hass.config_entries.async_forward_entry_setups(entry, ["cover"])
        return True
    except Exception as err:
        _LOGGER.error("Error setting up Dooya RS485: %s", err)
        return False

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["cover"])
    
    if unload_ok and entry.entry_id in hass.data[DOMAIN]:
        domain_data = hass.data[DOMAIN][entry.entry_id]
        if "controller" in domain_data:
            try:
                domain_data["controller"].serial.close()
            except Exception as err:
                _LOGGER.error("Error closing serial connection: %s", err)
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok

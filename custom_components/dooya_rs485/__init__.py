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
    _LOGGER.info("Setting up Dooya RS485 integration")
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Dooya RS485 from a config entry."""
    _LOGGER.info(
        "Setting up Dooya RS485 entry: name=%s, tcp_address=%s, tcp_port=%d, device_id_l=0x%02X, device_id_h=0x%02X",
        entry.data.get("name"),
        entry.data.get("tcp_address"),
        entry.data.get("tcp_port"),
        entry.data.get("device_id_l"),
        entry.data.get("device_id_h")
    )
    
    try:
        controller = DooyaController(
            tcp_port=entry.data["tcp_port"],
            tcp_address=entry.data["tcp_address"],
            device_id_l=entry.data["device_id_l"],
            device_id_h=entry.data["device_id_h"],
        )
        
        # Try to connect
        _LOGGER.info("Attempting to connect to device")
        await controller.connect()
        
        hass.data[DOMAIN][entry.entry_id] = {
            "data": entry.data,
            "controller": controller
        }
        
        _LOGGER.info("Setting up cover platform")
        await hass.config_entries.async_forward_entry_setups(entry, ["cover"])
        _LOGGER.info("Successfully set up Dooya RS485 entry")
        return True
    except Exception as err:
        _LOGGER.error("Error setting up Dooya RS485: %s", err)
        return False

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Dooya RS485 entry: %s", entry.data.get("name"))
    
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["cover"])
    
    if unload_ok and entry.entry_id in hass.data[DOMAIN]:
        domain_data = hass.data[DOMAIN][entry.entry_id]
        if "controller" in domain_data:
            try:
                _LOGGER.info("Disconnecting from device")
                await domain_data["controller"].disconnect()
            except Exception as err:
                _LOGGER.error("Error disconnecting from device: %s", err)
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.info("Successfully unloaded Dooya RS485 entry")
    else:
        _LOGGER.warning("Failed to unload platforms")
    
    return unload_ok

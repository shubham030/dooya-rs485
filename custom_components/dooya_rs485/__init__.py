from homeassistant import config_entries, core
from homeassistant.helpers.typing import ConfigType
from .const import DOMAIN

async def async_setup(hass: core.HomeAssistant, config: ConfigType) -> bool:
    """Set up the Dooya RS485 integration from configuration.yaml."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: core.HomeAssistant, entry: config_entries.ConfigEntry) -> bool:
    """Set up Dooya RS485 from a config entry."""
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = entry.data
    await hass.config_entries.async_forward_entry_setups(entry, ["cover"])

    return True

async def async_unload_entry(hass: core.HomeAssistant, entry: config_entries.ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["cover"])
    if unload_ok:
        hass.data[DOMAIN][entry.entry_id]["controller"].serial.close()
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

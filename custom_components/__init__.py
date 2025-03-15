from homeassistant import config_entries, core
from .const import DOMAIN

async def async_setup(hass: core.HomeAssistant, config: dict) -> bool:
    """Set up the Dooya Curtain Motor component from configuration.yaml."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: core.HomeAssistant, entry: config_entries.ConfigEntry) -> bool:
    """Set up Dooya Curtain Motor from a config entry."""
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = entry.data
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "cover")
    )
    return True

async def async_unload_entry(hass: core.HomeAssistant, entry: config_entries.ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "cover")
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
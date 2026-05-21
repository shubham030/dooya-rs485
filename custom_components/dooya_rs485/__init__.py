"""The Dooya RS485 integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, discovery
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_COVERS,
    CONF_DEVICE_ID_H,
    CONF_DEVICE_ID_L,
    CONF_TCP_ADDRESS,
    CONF_TCP_PORT,
    DEFAULT_DEVICE_ID_H,
    DEFAULT_TCP_PORT,
    DOMAIN,
)
from .dooya_rs485 import DooyaController

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.COVER]

# Update interval for polling
UPDATE_INTERVAL = timedelta(seconds=30)

# Connection timeout for initial setup (gateway may still be booting)
SETUP_TIMEOUT = 15


def hex_or_int(value: str | int) -> int:
    """Convert hex string or int to int."""
    if isinstance(value, int):
        return value
    try:
        return int(value, 0)
    except ValueError:
        raise vol.Invalid(f"Invalid value: {value}. Must be an integer or hex (e.g., 0xFE)")


COVER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_TCP_ADDRESS): cv.string,
        vol.Optional(CONF_TCP_PORT, default=DEFAULT_TCP_PORT): cv.port,
        vol.Required(CONF_DEVICE_ID_L): vol.All(vol.Coerce(hex_or_int), vol.Range(min=0, max=255)),
        vol.Optional(CONF_DEVICE_ID_H, default=DEFAULT_DEVICE_ID_H): vol.All(
            vol.Coerce(hex_or_int), vol.Range(min=0, max=255)
        ),
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_COVERS): vol.All(cv.ensure_list, [COVER_SCHEMA]),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Dooya RS485 component from YAML configuration."""
    hass.data.setdefault(DOMAIN, {"yaml_covers": [], "entries": {}})

    if DOMAIN not in config:
        return True

    domain_config = config[DOMAIN]
    covers = domain_config.get(CONF_COVERS, [])

    if covers:
        _LOGGER.info("Found %d Dooya covers in YAML configuration", len(covers))
        hass.data[DOMAIN]["yaml_covers"] = covers
        # Forward to cover platform for YAML-based setup
        hass.async_create_task(
            discovery.async_load_platform(
                hass, Platform.COVER, DOMAIN, {"source": "yaml"}, config
            )
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Dooya RS485 from a config entry."""
    hass.data.setdefault(DOMAIN, {"yaml_covers": [], "entries": {}})

    _LOGGER.info(
        "Setting up Dooya RS485 entry: name=%s, tcp_address=%s, tcp_port=%d, device_id_l=0x%02X, device_id_h=0x%02X",
        entry.data.get("name"),
        entry.data.get("tcp_address"),
        entry.data.get("tcp_port"),
        entry.data.get("device_id_l"),
        entry.data.get("device_id_h"),
    )

    controller = DooyaController(
        tcp_port=entry.data["tcp_port"],
        tcp_address=entry.data["tcp_address"],
        device_id_l=entry.data["device_id_l"],
        device_id_h=entry.data["device_id_h"],
    )

    # Try to connect - raise ConfigEntryNotReady if it fails
    # This tells Home Assistant to retry automatically
    _LOGGER.info("Attempting to connect to device")
    try:
        connected = await controller.connect()
        if not connected:
            raise ConfigEntryNotReady(
                f"Failed to connect to Dooya device at {entry.data['tcp_address']}:{entry.data['tcp_port']}"
            )
    except ConfigEntryNotReady:
        raise
    except Exception as err:
        _LOGGER.error("Connection error: %s", err)
        raise ConfigEntryNotReady(
            f"Error connecting to Dooya device: {err}"
        ) from err

    # Create coordinator for data updates
    coordinator = DooyaDataUpdateCoordinator(
        hass,
        controller=controller,
        name=entry.data.get("name", "Dooya Cover"),
    )

    # Fetch initial data - if this fails, raise ConfigEntryNotReady
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        # Clean up the connection before raising
        await controller.disconnect()
        raise ConfigEntryNotReady(
            f"Failed to fetch initial data from device: {err}"
        ) from err

    hass.data[DOMAIN]["entries"][entry.entry_id] = {
        "data": entry.data,
        "controller": controller,
        "coordinator": coordinator,
    }

    _LOGGER.info("Setting up cover platform")
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info("Successfully set up Dooya RS485 entry")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Dooya RS485 entry: %s", entry.data.get("name"))

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok and entry.entry_id in hass.data[DOMAIN]["entries"]:
        domain_data = hass.data[DOMAIN]["entries"][entry.entry_id]
        if "controller" in domain_data:
            try:
                _LOGGER.info("Disconnecting from device")
                await domain_data["controller"].disconnect()
            except Exception as err:
                _LOGGER.error("Error disconnecting from device: %s", err)
        hass.data[DOMAIN]["entries"].pop(entry.entry_id)
        _LOGGER.info("Successfully unloaded Dooya RS485 entry")
    else:
        _LOGGER.warning("Failed to unload platforms")

    return unload_ok


class DooyaDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Dooya data."""

    def __init__(
        self,
        hass: HomeAssistant,
        controller: DooyaController,
        name: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"Dooya {name}",
            update_interval=UPDATE_INTERVAL,
        )
        self.controller = controller
        self._consecutive_errors = 0
        self._max_consecutive_errors = 5  # Allow more retries before failing

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the device."""
        try:
            # Ensure connection before fetching data
            if not self.controller.is_connected:
                connected = await self.controller.ensure_connected()
                if not connected:
                    self._consecutive_errors += 1
                    _LOGGER.warning(
                        "Connection failed (attempt %d/%d)",
                        self._consecutive_errors,
                        self._max_consecutive_errors,
                    )
                    if self._consecutive_errors >= self._max_consecutive_errors:
                        raise UpdateFailed(
                            f"Failed to connect after {self._max_consecutive_errors} attempts"
                        )
                    # Return last known data if available, otherwise empty dict
                    return self.data if self.data else {}

            # Read all status in one coordinated call
            data = await self.controller.read_all_status()

            # Reset error counter on success
            if self._consecutive_errors > 0:
                _LOGGER.info("Connection restored after %d failed attempts", self._consecutive_errors)
            self._consecutive_errors = 0

            return data

        except UpdateFailed:
            raise
        except Exception as err:
            self._consecutive_errors += 1
            _LOGGER.warning(
                "Error fetching data (attempt %d/%d): %s",
                self._consecutive_errors,
                self._max_consecutive_errors,
                err,
            )

            if self._consecutive_errors >= self._max_consecutive_errors:
                raise UpdateFailed(f"Error communicating with device: {err}") from err

            # Return last known data if available
            return self.data if self.data else {}

"""The Dooya RS485 integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, MOTOR_STATUS_OPENING, MOTOR_STATUS_CLOSING
from .dooya_rs485 import DooyaController

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.COVER]

# Update interval for polling while idle
UPDATE_INTERVAL = timedelta(seconds=30)

# Faster polling while the motor is moving, so the position tracks smoothly
MOVING_UPDATE_INTERVAL = timedelta(seconds=2)

# Keep polling fast for a short window after a movement command, to bridge the
# brief delay before the motor reports that it has started moving.
MOVEMENT_BOOST_SECONDS = 8.0


def _stroke_issue_id(entry_id: str) -> str:
    """Return the repair-issue id for an entry's uncalibrated stroke."""
    return f"stroke_not_set_{entry_id}"

# Connection timeout for initial setup (gateway may still be booting)
SETUP_TIMEOUT = 15

# This integration is config entry only (no YAML configuration)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Dooya RS485 from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
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
        entry_id=entry.entry_id,
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

    # Read static device configuration/identity once (used for device info and
    # diagnostic attributes). These registers don't change at runtime, so they
    # are intentionally left out of the polling loop.
    try:
        device_attributes = await controller.read_device_attributes()
    except Exception as err:
        _LOGGER.warning("Could not read device attributes: %s", err)
        device_attributes = {}

    hass.data[DOMAIN][entry.entry_id] = {
        "data": entry.data,
        "controller": controller,
        "coordinator": coordinator,
        "device_attributes": device_attributes,
    }

    # Reload the entry when its options/data change so edits take effect.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _LOGGER.info("Setting up cover platform")
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info("Successfully set up Dooya RS485 entry")
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when its configuration changes."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Dooya RS485 entry: %s", entry.data.get("name"))

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok and entry.entry_id in hass.data[DOMAIN]:
        domain_data = hass.data[DOMAIN][entry.entry_id]
        if "controller" in domain_data:
            try:
                _LOGGER.info("Disconnecting from device")
                await domain_data["controller"].disconnect()
            except Exception as err:
                _LOGGER.error("Error disconnecting from device: %s", err)
        # Clear any repair issue raised for this entry.
        ir.async_delete_issue(hass, DOMAIN, _stroke_issue_id(entry.entry_id))
        hass.data[DOMAIN].pop(entry.entry_id)
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
        entry_id: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"Dooya {name}",
            update_interval=UPDATE_INTERVAL,
        )
        self.controller = controller
        self._entry_id = entry_id
        self._device_name = name
        self._consecutive_errors = 0
        self._max_consecutive_errors = 5  # Allow more retries before failing
        self._boost_deadline = 0.0

    @callback
    def async_boost_polling(self) -> None:
        """Poll quickly for a short window after a movement command."""
        self._boost_deadline = self.hass.loop.time() + MOVEMENT_BOOST_SECONDS
        self.update_interval = MOVING_UPDATE_INTERVAL

    def _next_interval(self, motor_status: int | None) -> timedelta:
        """Choose the polling interval based on movement and boost window."""
        moving = motor_status in (MOTOR_STATUS_OPENING, MOTOR_STATUS_CLOSING)
        if moving or self.hass.loop.time() < self._boost_deadline:
            return MOVING_UPDATE_INTERVAL
        return UPDATE_INTERVAL

    @callback
    def _async_update_stroke_issue(self, stroke_set: bool | None) -> None:
        """Raise or clear the 'stroke not set' repair issue."""
        issue_id = _stroke_issue_id(self._entry_id)
        if stroke_set is False:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="stroke_not_set",
                translation_placeholders={"name": self._device_name},
            )
        elif stroke_set is True:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

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

            # Read runtime status (position + motor status) in one coordinated call
            data = await self.controller.read_status()

            # Reset error counter on success
            if self._consecutive_errors > 0:
                _LOGGER.info("Connection restored after %d failed attempts", self._consecutive_errors)
            self._consecutive_errors = 0

            # Poll faster while moving; raise/clear the calibration repair issue.
            self.update_interval = self._next_interval(data.get("motor_status"))
            self._async_update_stroke_issue(data.get("stroke_set"))

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

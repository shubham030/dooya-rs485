"""Cover platform for Dooya RS485 integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import voluptuous as vol

from .const import (
    DOMAIN,
    DIRECTION_DEFAULT,
    DIRECTION_REVERSED,
    MANUAL_ENABLE_ON,
    MANUAL_ENABLE_OFF,
    MOTOR_STATUS_STOPPED,
    MOTOR_STATUS_OPENING,
    MOTOR_STATUS_CLOSING,
    MOTOR_STATUS_SETTING,
    SWITCH_ACTIVE_TYPES,
    SWITCH_PASSIVE_TYPES,
)

_LOGGER = logging.getLogger(__name__)

SUPPORTED_FEATURES = (
    CoverEntityFeature.OPEN
    | CoverEntityFeature.CLOSE
    | CoverEntityFeature.STOP
    | CoverEntityFeature.SET_POSITION
)

MOTOR_STATUS_LABELS = {
    MOTOR_STATUS_STOPPED: "stopped",
    MOTOR_STATUS_OPENING: "opening",
    MOTOR_STATUS_CLOSING: "closing",
    MOTOR_STATUS_SETTING: "setting",
}

DIRECTION_LABELS = {
    DIRECTION_DEFAULT: "default",
    DIRECTION_REVERSED: "reversed",
}

MANUAL_ENABLE_LABELS = {
    MANUAL_ENABLE_ON: "enabled",
    MANUAL_ENABLE_OFF: "disabled",
}


def _label(mapping: dict[int, str], value: int | None) -> str:
    """Map a raw register value to a human-readable label."""
    if value is None:
        return "unknown"
    return mapping.get(value, f"unknown ({value})")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dooya RS485 cover from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    controller = data["controller"]
    name = data["data"]["name"]
    device_attributes = data.get("device_attributes", {})

    _LOGGER.info("Setting up cover entity with name: %s", name)
    async_add_entities(
        [DooyaCover(coordinator, controller, name, entry.entry_id, device_attributes)]
    )

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "program_address",
        {
            vol.Required("address_low"): vol.All(vol.Coerce(int), vol.Range(min=1, max=254)),
            vol.Required("address_high"): vol.All(vol.Coerce(int), vol.Range(min=1, max=254)),
        },
        "async_program_address",
    )


class DooyaCover(CoordinatorEntity, CoverEntity):
    """Representation of a Dooya RS485 cover."""

    _attr_has_entity_name = True
    _attr_name = None  # Main feature of the device; inherit the device name.
    _attr_device_class = CoverDeviceClass.CURTAIN
    _attr_supported_features = SUPPORTED_FEATURES

    def __init__(
        self,
        coordinator,
        controller,
        name: str,
        entry_id: str,
        device_attributes: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the cover."""
        super().__init__(coordinator)
        _LOGGER.info("Initializing DooyaCover with name: %s", name)
        self._controller = controller
        self._device_attributes = device_attributes or {}
        self._attr_unique_id = f"dooya_{entry_id}"

        sw_version = self._device_attributes.get("software_version")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=name,
            manufacturer="Dooya",
            model="RS485 Curtain Motor",
            sw_version=str(sw_version) if sw_version is not None else None,
        )

    @property
    def current_cover_position(self) -> int | None:
        """Return current position of cover (0 closed, 100 open)."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("position")

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed."""
        position = self.current_cover_position
        if position is None:
            return None
        return position == 0

    @property
    def is_opening(self) -> bool | None:
        """Return if the cover is opening (from motor status)."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("motor_status") == MOTOR_STATUS_OPENING

    @property
    def is_closing(self) -> bool | None:
        """Return if the cover is closing (from motor status)."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("motor_status") == MOTOR_STATUS_CLOSING

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs: dict[str, Any] = {
            "motor_status": _label(
                MOTOR_STATUS_LABELS,
                self.coordinator.data.get("motor_status") if self.coordinator.data else None,
            ),
            "direction": _label(DIRECTION_LABELS, self._device_attributes.get("direction")),
            "hand_pull_start": _label(
                MANUAL_ENABLE_LABELS, self._device_attributes.get("manual_enable")
            ),
            "passive_switch_type": _label(
                SWITCH_PASSIVE_TYPES, self._device_attributes.get("switch_type_passive")
            ),
            "active_switch_type": _label(
                SWITCH_ACTIVE_TYPES, self._device_attributes.get("switch_type_active")
            ),
        }
        return attrs

    async def _async_refresh_after_command(self) -> None:
        """Poll quickly for a while so the position tracks the movement."""
        self.coordinator.async_boost_polling()
        await self.coordinator.async_request_refresh()

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        try:
            await self._controller.open()
            await self._async_refresh_after_command()
        except Exception as err:
            _LOGGER.error("Error opening cover: %s", err)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        try:
            await self._controller.close()
            await self._async_refresh_after_command()
        except Exception as err:
            _LOGGER.error("Error closing cover: %s", err)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        try:
            await self._controller.stop()
            await self._async_refresh_after_command()
        except Exception as err:
            _LOGGER.error("Error stopping cover: %s", err)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        try:
            position = kwargs.get("position")
            if position is not None:
                _LOGGER.info("Setting cover position to %d%%", position)
                await self._controller.set_cover_position(position)
                await self._async_refresh_after_command()
        except Exception as err:
            _LOGGER.error("Error setting cover position: %s", err)

    async def async_toggle(self, **kwargs: Any) -> None:
        """Toggle the cover using the motor's native negate command (0x0F)."""
        try:
            await self._controller.toggle()
            await self._async_refresh_after_command()
        except Exception as err:
            _LOGGER.error("Error toggling cover: %s", err)

    async def async_program_address(self, address_low: int, address_high: int) -> None:
        """Program new device address."""
        try:
            success = await self._controller.program_device_address(address_low, address_high)
            if success:
                _LOGGER.info(
                    "Successfully programmed new address: 0x%02X%02X",
                    address_high,
                    address_low,
                )
            else:
                _LOGGER.error("Failed to program new address")
        except Exception as err:
            _LOGGER.error("Error programming address: %s", err)

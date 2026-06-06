"""Switch platform for Dooya RS485 boolean configuration registers."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CURTAIN_READ_WRITE_DIRECTION,
    CURTAIN_READ_WRITE_MANUAL_ENABLE,
    DIRECTION_DEFAULT,
    DIRECTION_REVERSED,
    DOMAIN,
    MANUAL_ENABLE_OFF,
    MANUAL_ENABLE_ON,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Dooya RS485 configuration switches."""
    data = hass.data[DOMAIN][entry.entry_id]
    controller = data["controller"]
    device_attributes = data.get("device_attributes", {})

    async_add_entities(
        [
            # "On" = reversed direction.
            DooyaConfigSwitch(
                controller,
                entry.entry_id,
                translation_key="reverse_direction",
                register=CURTAIN_READ_WRITE_DIRECTION,
                attr_key="direction",
                on_value=DIRECTION_REVERSED,
                off_value=DIRECTION_DEFAULT,
                device_attributes=device_attributes,
            ),
            # "On" = hand-pull start enabled (register value 0x00).
            DooyaConfigSwitch(
                controller,
                entry.entry_id,
                translation_key="hand_pull_start",
                register=CURTAIN_READ_WRITE_MANUAL_ENABLE,
                attr_key="manual_enable",
                on_value=MANUAL_ENABLE_ON,
                off_value=MANUAL_ENABLE_OFF,
                device_attributes=device_attributes,
            ),
        ]
    )


class DooyaConfigSwitch(SwitchEntity):
    """A writable Dooya boolean configuration register exposed as a switch."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        controller,
        entry_id: str,
        *,
        translation_key: str,
        register: int,
        attr_key: str,
        on_value: int,
        off_value: int,
        device_attributes: dict | None,
    ) -> None:
        """Initialize the switch."""
        self._controller = controller
        self._register = register
        self._on_value = on_value
        self._off_value = off_value
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"dooya_{entry_id}_{translation_key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry_id)})

        raw = (device_attributes or {}).get(attr_key)
        self._attr_is_on = None if raw is None else raw == on_value

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Write the 'on' value to the device."""
        if await self._controller.write_register(self._register, self._on_value):
            self._attr_is_on = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on %s", self._attr_translation_key)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Write the 'off' value to the device."""
        if await self._controller.write_register(self._register, self._off_value):
            self._attr_is_on = False
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn off %s", self._attr_translation_key)

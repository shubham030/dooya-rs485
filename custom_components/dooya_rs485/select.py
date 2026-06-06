"""Select platform for Dooya RS485 configuration registers."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CURTAIN_READ_WRITE_SWITCH_ACTIVE,
    CURTAIN_READ_WRITE_SWITCH_PASSIVE,
    DOMAIN,
    SWITCH_ACTIVE_TYPES,
    SWITCH_PASSIVE_TYPES,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Dooya RS485 configuration selects."""
    data = hass.data[DOMAIN][entry.entry_id]
    controller = data["controller"]
    device_attributes = data.get("device_attributes", {})

    async_add_entities(
        [
            DooyaConfigSelect(
                controller,
                entry.entry_id,
                translation_key="passive_switch_type",
                register=CURTAIN_READ_WRITE_SWITCH_PASSIVE,
                attr_key="switch_type_passive",
                options_map=SWITCH_PASSIVE_TYPES,
                device_attributes=device_attributes,
            ),
            DooyaConfigSelect(
                controller,
                entry.entry_id,
                translation_key="active_switch_type",
                register=CURTAIN_READ_WRITE_SWITCH_ACTIVE,
                attr_key="switch_type_active",
                options_map=SWITCH_ACTIVE_TYPES,
                device_attributes=device_attributes,
            ),
        ]
    )


class DooyaConfigSelect(SelectEntity):
    """A writable Dooya configuration register exposed as a select."""

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
        options_map: dict[int, str],
        device_attributes: dict | None,
    ) -> None:
        """Initialize the select."""
        self._controller = controller
        self._register = register
        self._value_to_label = options_map
        self._label_to_value = {label: value for value, label in options_map.items()}
        self._attr_options = list(options_map.values())
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"dooya_{entry_id}_{translation_key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry_id)})

        raw = (device_attributes or {}).get(attr_key)
        self._attr_current_option = options_map.get(raw)

    async def async_select_option(self, option: str) -> None:
        """Write the selected option to the device."""
        value = self._label_to_value.get(option)
        if value is None:
            _LOGGER.error("Unknown option %s for %s", option, self._attr_translation_key)
            return
        if await self._controller.write_register(self._register, value):
            self._attr_current_option = option
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to set %s to %s", self._attr_translation_key, option)

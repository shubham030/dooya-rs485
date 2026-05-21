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
from homeassistant.const import (
    CONF_NAME,
    STATE_CLOSED,
    STATE_CLOSING,
    STATE_OPEN,
    STATE_OPENING,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import voluptuous as vol

from .const import (
    CONF_DEVICE_ID_H,
    CONF_DEVICE_ID_L,
    CONF_TCP_ADDRESS,
    CONF_TCP_PORT,
    DEFAULT_DEVICE_ID_H,
    DEFAULT_TCP_PORT,
    DOMAIN,
    STATE_ERROR,
    SUPPORTED_FEATURES,
)
from .dooya_rs485 import DooyaController

_LOGGER = logging.getLogger(__name__)

# Motor Status Constants
MOTOR_STATUS_STOPPED = 0x00
MOTOR_STATUS_RUNNING = 0x01
MOTOR_STATUS_ERROR = 0x02

# Switch Status Constants
SWITCH_STATUS_NORMAL = 0x00
SWITCH_STATUS_TRIGGERED = 0x01

# Handle Status Constants
HANDLE_STATUS_NORMAL = 0x00
HANDLE_STATUS_OPERATED = 0x01


async def async_setup_platform(
    hass: HomeAssistant,
    config: dict,
    async_add_entities: AddEntitiesCallback,
    discovery_info: dict | None = None,
) -> None:
    """Set up Dooya RS485 covers from YAML configuration."""
    if discovery_info is None or discovery_info.get("source") != "yaml":
        return

    yaml_covers = hass.data[DOMAIN].get("yaml_covers", [])
    if not yaml_covers:
        return

    entities = []
    for cover_config in yaml_covers:
        name = cover_config[CONF_NAME]
        tcp_address = cover_config[CONF_TCP_ADDRESS]
        tcp_port = cover_config.get(CONF_TCP_PORT, DEFAULT_TCP_PORT)
        device_id_l = cover_config[CONF_DEVICE_ID_L]
        device_id_h = cover_config.get(CONF_DEVICE_ID_H, DEFAULT_DEVICE_ID_H)

        _LOGGER.info(
            "Setting up YAML cover: name=%s, tcp_address=%s, tcp_port=%d, device_id_l=0x%02X, device_id_h=0x%02X",
            name,
            tcp_address,
            tcp_port,
            device_id_l,
            device_id_h,
        )

        controller = DooyaController(
            tcp_port=tcp_port,
            tcp_address=tcp_address,
            device_id_l=device_id_l,
            device_id_h=device_id_h,
        )

        entity = DooyaCoverYAML(controller, name)
        entities.append(entity)

    if entities:
        async_add_entities(entities)
        _LOGGER.info("Added %d YAML-configured Dooya covers", len(entities))

        # Register service on first entity's platform
        platform = entity_platform.async_get_current_platform()
        platform.async_register_entity_service(
            "program_address",
            {
                vol.Required("address_low"): vol.All(vol.Coerce(int), vol.Range(min=1, max=254)),
                vol.Required("address_high"): vol.All(vol.Coerce(int), vol.Range(min=1, max=254)),
            },
            "async_program_address",
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dooya RS485 cover from a config entry."""
    data = hass.data[DOMAIN]["entries"][entry.entry_id]
    coordinator = data["coordinator"]
    controller = data["controller"]
    name = data["data"]["name"]

    _LOGGER.info("Setting up cover entity with name: %s", name)
    async_add_entities([DooyaCover(coordinator, controller, name, entry.entry_id)])

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "program_address",
        {
            vol.Required("address_low"): vol.All(vol.Coerce(int), vol.Range(min=1, max=254)),
            vol.Required("address_high"): vol.All(vol.Coerce(int), vol.Range(min=1, max=254)),
        },
        "async_program_address",
    )


class DooyaCoverBase(CoverEntity):
    """Base class for Dooya RS485 covers."""

    _attr_has_entity_name = True
    _attr_device_class = CoverDeviceClass.CURTAIN

    def __init__(self, controller: DooyaController, name: str) -> None:
        """Initialize the cover."""
        self._name = name
        self._controller = controller
        self._target_position: int | None = None
        self._last_position: int | None = None
        self._data: dict[str, Any] = {}

    @property
    def name(self) -> str:
        """Return the name of the cover."""
        return self._name

    @property
    def supported_features(self) -> CoverEntityFeature:
        """Flag supported features."""
        return SUPPORTED_FEATURES | CoverEntityFeature.SET_POSITION

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed."""
        position = self.current_cover_position
        if position is None:
            return None
        return position == 0

    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening."""
        return self.state == STATE_OPENING

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing."""
        return self.state == STATE_CLOSING

    def _get_state_from_data(self, data: dict[str, Any] | None) -> str:
        """Determine state from data dict."""
        if data is None:
            return STATE_UNKNOWN

        motor_status = data.get("motor_status")
        if motor_status == MOTOR_STATUS_ERROR:
            return STATE_ERROR

        position = data.get("position")
        if position is None:
            return STATE_UNKNOWN

        # If we have a target position, check if we're moving
        if self._target_position is not None:
            if abs(position - self._target_position) <= 5:  # 5% tolerance
                self._target_position = None
            elif position < self._target_position:
                return STATE_OPENING
            else:
                return STATE_CLOSING

        # Determine state from position change
        if self._last_position is not None and position != self._last_position:
            if position > self._last_position:
                return STATE_OPENING
            return STATE_CLOSING

        # Static position
        if position == 0:
            return STATE_CLOSED
        if position == 100:
            return STATE_OPEN
        return STATE_OPEN if position > 50 else STATE_CLOSED

    def _format_motor_status(self, status: int | None) -> str:
        """Format motor status for display."""
        if status is None:
            return "unknown"
        if status == MOTOR_STATUS_STOPPED:
            return "stopped"
        if status == MOTOR_STATUS_RUNNING:
            return "running"
        if status == MOTOR_STATUS_ERROR:
            return "error"
        return f"unknown ({status})"

    def _format_switch_status(self, status: int | None) -> str:
        """Format switch status for display."""
        if status is None:
            return "unknown"
        if status == SWITCH_STATUS_NORMAL:
            return "normal"
        if status == SWITCH_STATUS_TRIGGERED:
            return "triggered"
        return f"unknown ({status})"

    def _format_handle_status(self, status: int | None) -> str:
        """Format handle status for display."""
        if status is None:
            return "unknown"
        if status == HANDLE_STATUS_NORMAL:
            return "normal"
        if status == HANDLE_STATUS_OPERATED:
            return "operated"
        return f"unknown ({status})"

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        try:
            await self._controller.ensure_connected()
            await self._controller.open()
            self._target_position = 100
            await self.async_update()
        except Exception as err:
            _LOGGER.error("Error opening cover: %s", err)
            self._target_position = None

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        try:
            await self._controller.ensure_connected()
            await self._controller.close()
            self._target_position = 0
            await self.async_update()
        except Exception as err:
            _LOGGER.error("Error closing cover: %s", err)
            self._target_position = None

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        try:
            await self._controller.ensure_connected()
            await self._controller.stop()
            self._target_position = None
            await self.async_update()
        except Exception as err:
            _LOGGER.error("Error stopping cover: %s", err)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        try:
            position = kwargs.get("position")
            if position is not None:
                _LOGGER.info("Setting cover position to %d%%", position)
                await self._controller.ensure_connected()
                await self._controller.set_cover_position(position)
                self._target_position = position
                await self.async_update()
        except Exception as err:
            _LOGGER.error("Error setting cover position: %s", err)
            self._target_position = None

    async def async_program_address(self, address_low: int, address_high: int) -> None:
        """Program new device address."""
        try:
            await self._controller.ensure_connected()
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


class DooyaCoverYAML(DooyaCoverBase):
    """Representation of a YAML-configured Dooya RS485 cover."""

    def __init__(self, controller: DooyaController, name: str) -> None:
        """Initialize the cover."""
        super().__init__(controller, name)
        self._attr_unique_id = f"dooya_yaml_{name.lower().replace(' ', '_')}"
        _LOGGER.info(
            "YAML Cover entity initialized with name: %s, unique_id: %s",
            self._name,
            self._attr_unique_id,
        )

    @property
    def state(self) -> str:
        """Return the state of the cover."""
        return self._get_state_from_data(self._data)

    @property
    def current_cover_position(self) -> int | None:
        """Return current position of cover."""
        return self._data.get("position")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self._data:
            return {}

        return {
            "motor_status": self._format_motor_status(self._data.get("motor_status")),
            "active_switch_status": self._format_switch_status(
                self._data.get("active_switch")
            ),
            "passive_switch_status": self._format_switch_status(
                self._data.get("passive_switch")
            ),
            "handle_status": self._format_handle_status(
                self._data.get("handle_status")
            ),
        }

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        # Connect and get initial state
        try:
            await self._controller.connect()
            await self.async_update()
        except Exception as err:
            _LOGGER.error("Error connecting to device on startup: %s", err)

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        try:
            await self._controller.disconnect()
        except Exception as err:
            _LOGGER.error("Error disconnecting from device: %s", err)

    async def async_update(self) -> None:
        """Fetch new state data for this cover."""
        try:
            if not self._controller.is_connected:
                await self._controller.ensure_connected()

            self._data = await self._controller.read_all_status()

            # Update last position for state tracking
            current = self._data.get("position")
            if current is not None:
                self._last_position = current
        except Exception as err:
            _LOGGER.warning("Error updating cover state: %s", err)


class DooyaCover(CoordinatorEntity, DooyaCoverBase):
    """Representation of a config-entry Dooya RS485 cover."""

    def __init__(self, coordinator, controller: DooyaController, name: str, entry_id: str) -> None:
        """Initialize the cover."""
        CoordinatorEntity.__init__(self, coordinator)
        DooyaCoverBase.__init__(self, controller, name)
        self._attr_unique_id = f"dooya_{entry_id}"
        _LOGGER.info(
            "Cover entity initialized with name: %s, unique_id: %s",
            self._name,
            self._attr_unique_id,
        )

    @property
    def state(self) -> str:
        """Return the state of the cover."""
        return self._get_state_from_data(self.coordinator.data)

    @property
    def current_cover_position(self) -> int | None:
        """Return current position of cover."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("position")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if self.coordinator.data is None:
            return {}

        return {
            "motor_status": self._format_motor_status(self.coordinator.data.get("motor_status")),
            "active_switch_status": self._format_switch_status(
                self.coordinator.data.get("active_switch")
            ),
            "passive_switch_status": self._format_switch_status(
                self.coordinator.data.get("passive_switch")
            ),
            "handle_status": self._format_handle_status(
                self.coordinator.data.get("handle_status")
            ),
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Update last position for state tracking
        if self.coordinator.data:
            current = self.coordinator.data.get("position")
            if current is not None:
                self._last_position = current
        super()._handle_coordinator_update()

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        try:
            await self._controller.open()
            self._target_position = 100
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Error opening cover: %s", err)
            self._target_position = None

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        try:
            await self._controller.close()
            self._target_position = 0
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Error closing cover: %s", err)
            self._target_position = None

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        try:
            await self._controller.stop()
            self._target_position = None
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Error stopping cover: %s", err)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        try:
            position = kwargs.get("position")
            if position is not None:
                _LOGGER.info("Setting cover position to %d%%", position)
                await self._controller.set_cover_position(position)
                self._target_position = position
                await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Error setting cover position: %s", err)
            self._target_position = None

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

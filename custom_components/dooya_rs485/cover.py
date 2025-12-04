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

from .const import DOMAIN, STATE_ERROR, SUPPORTED_FEATURES

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


class DooyaCover(CoordinatorEntity, CoverEntity):
    """Representation of a Dooya RS485 cover."""

    _attr_has_entity_name = True
    _attr_device_class = CoverDeviceClass.CURTAIN

    def __init__(self, coordinator, controller, name: str, entry_id: str) -> None:
        """Initialize the cover."""
        super().__init__(coordinator)
        _LOGGER.info("Initializing DooyaCover with name: %s", name)
        self._name = name
        self._controller = controller
        self._attr_unique_id = f"dooya_{entry_id}"
        self._target_position: int | None = None
        self._last_position: int | None = None
        _LOGGER.info(
            "Cover entity initialized with name: %s, unique_id: %s",
            self._name,
            self._attr_unique_id,
        )

    @property
    def name(self) -> str:
        """Return the name of the cover."""
        return self._name

    @property
    def state(self) -> str:
        """Return the state of the cover."""
        if self.coordinator.data is None:
            return STATE_UNKNOWN

        motor_status = self.coordinator.data.get("motor_status")
        if motor_status == MOTOR_STATUS_ERROR:
            return STATE_ERROR

        position = self.coordinator.data.get("position")
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

    @property
    def current_cover_position(self) -> int | None:
        """Return current position of cover."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("position")

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
            # Request immediate update
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Error opening cover: %s", err)
            self._target_position = None

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        try:
            await self._controller.close()
            self._target_position = 0
            # Request immediate update
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Error closing cover: %s", err)
            self._target_position = None

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        try:
            await self._controller.stop()
            self._target_position = None
            # Request immediate update
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
                # Request immediate update
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

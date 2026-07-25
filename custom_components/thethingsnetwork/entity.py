"""Support for The Things Network entities."""

import logging

from ttn_client import TTNBaseValue

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_APP_ID, DOMAIN
from .coordinator import TTNCoordinator

_LOGGER = logging.getLogger(__name__)


def latest_ttn_value(device_data: dict[str, TTNBaseValue]) -> TTNBaseValue | None:
    """Return a value from the most recent uplink of a device, or None."""

    return max(device_data.values(), key=lambda value: value.received_at, default=None)


def known_device_ids(hass: HomeAssistant, entry: ConfigEntry) -> set[str]:
    """Return the device_ids already registered for this config entry.

    The coordinator only ever carries uplinks newer than the last poll, so a device
    that has been quiet for longer than first_fetch_h is absent from its data and
    would get no entities at all after a restart.
    """

    prefix = f"{entry.data[CONF_APP_ID]}_"
    return {
        identifier[1].removeprefix(prefix)
        for device in dr.async_entries_for_config_entry(
            dr.async_get(hass), entry.entry_id
        )
        for identifier in device.identifiers
        if identifier[0] == DOMAIN and identifier[1].startswith(prefix)
    }


class TTNEntity(CoordinatorEntity[TTNCoordinator]):
    """Representation of a The Things Network Data Storage sensor."""

    _attr_has_entity_name = True
    _ttn_value: TTNBaseValue

    def __init__(
        self,
        coordinator: TTNCoordinator,
        app_id: str,
        ttn_value: TTNBaseValue,
    ) -> None:
        """Initialize a The Things Network Data Storage sensor."""

        # Pass coordinator to CoordinatorEntity
        super().__init__(coordinator)

        self._ttn_value = ttn_value

        self._attr_unique_id = f"{self.device_id}_{self.field_id}"
        self._attr_name = self.field_id

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{app_id}_{self.device_id}")},
            name=self.device_id,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        update = self.coordinator.data.get(self.device_id, {}).get(self.field_id)
        if update is None or update.received_at <= self._ttn_value.received_at:
            return

        if update.value is None:
            # Legacy uplink without a usable value: keep the last known state rather
            # than blanking the entity.
            _LOGGER.debug("Skipping update for %s: value is None", self.unique_id)
            return

        # The type of an entity must not change after its creation
        if not isinstance(update, type(self._ttn_value)):
            _LOGGER.warning(
                "Ignoring update for %s: type changed from %s to %s",
                self.unique_id,
                type(self._ttn_value).__name__,
                type(update).__name__,
            )
            return

        _LOGGER.debug("Received update for %s: %s", self.unique_id, update)
        self._ttn_value = update
        self.async_write_ha_state()

    @property
    def device_id(self) -> str:
        """Return device_id."""
        return str(self._ttn_value.device_id)

    @property
    def field_id(self) -> str:
        """Return field_id."""
        return str(self._ttn_value.field_id)


class TTNDeviceEntity(CoordinatorEntity[TTNCoordinator]):
    """Base for entities describing a TTN device as a whole, not a single field."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TTNCoordinator,
        app_id: str,
        device_id: str,
        key: str,
    ) -> None:
        """Initialize a device wide The Things Network entity."""

        super().__init__(coordinator)

        self._device_id = device_id

        self._attr_unique_id = f"{device_id}_{key}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{app_id}_{device_id}")},
            name=device_id,
        )

    @property
    def device_data(self) -> dict[str, TTNBaseValue]:
        """Return the values received for this device in the latest update."""

        return self.coordinator.data.get(self._device_id, {})

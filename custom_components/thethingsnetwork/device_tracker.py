"""The Things Network device tracker platform."""

from __future__ import annotations

import logging

from ttn_client import TTNBaseValue

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_LATITUDE, ATTR_LONGITUDE, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_APP_ID, DOMAIN, FIELD_LATITUDE, FIELD_LONGITUDE, KEY_TRACKER
from .coordinator import TTNCoordinator
from .entity import TTNDeviceEntity

_LOGGER = logging.getLogger(__name__)


def _gps_fix(device_uplinks: dict[str, TTNBaseValue]) -> tuple[float, float] | None:
    """Return the latitude/longitude of a device, or None without a complete fix.

    The decoder omits invalid fields entirely rather than sending null, so a missing
    key means "no update" - and a 0/0 fix is already discarded decoder side.
    """

    latitude = device_uplinks.get(FIELD_LATITUDE)
    longitude = device_uplinks.get(FIELD_LONGITUDE)

    if latitude is None or longitude is None:
        return None

    if latitude.value is None or longitude.value is None:
        return None

    try:
        return float(latitude.value), float(longitude.value)
    except (ValueError, TypeError):
        _LOGGER.warning(
            "Ignoring GPS fix with non-numeric coordinates: %s / %s",
            latitude.value,
            longitude.value,
        )
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up TTN device trackers from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    app_id = entry.data[CONF_APP_ID]

    # Devices that already had a tracker keep it across restarts, even when their last
    # fix predates the coordinator's backfill window - RestoreEntity puts the marker
    # back on the map. Devices without GPS never get a tracker at all.
    suffix = f"_{KEY_TRACKER}"
    trackers: set[str] = {
        registry_entry.unique_id.removesuffix(suffix)
        for registry_entry in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
        if registry_entry.domain == Platform.DEVICE_TRACKER
        and registry_entry.unique_id.endswith(suffix)
    }
    async_add_entities(
        TtnDeviceTracker(coordinator, app_id, device_id) for device_id in trackers
    )

    def _async_measurement_listener() -> None:
        """Create a tracker for every device that reports its first GPS fix."""
        new_trackers: list[TtnDeviceTracker] = []

        for device_id, device_uplinks in coordinator.data.items():
            if device_id in trackers:
                continue

            if _gps_fix(device_uplinks) is None:
                continue

            trackers.add(device_id)
            new_trackers.append(TtnDeviceTracker(coordinator, app_id, device_id))

        if new_trackers:
            async_add_entities(new_trackers)

    entry.async_on_unload(coordinator.async_add_listener(_async_measurement_listener))
    _async_measurement_listener()


class TtnDeviceTracker(TTNDeviceEntity, TrackerEntity, RestoreEntity):
    """Map marker for a TTN device, fed from the latitude/longitude fields."""

    _attr_name = None
    _attr_source_type = SourceType.GPS

    def __init__(
        self, coordinator: TTNCoordinator, app_id: str, device_id: str
    ) -> None:
        """Initialize the device tracker."""
        super().__init__(coordinator, app_id, device_id, KEY_TRACKER)

    async def async_added_to_hass(self) -> None:
        """Restore the last position and adopt any data already fetched."""
        await super().async_added_to_hass()

        if (state := await self.async_get_last_state()) is not None:
            self._attr_latitude = state.attributes.get(ATTR_LATITUDE)
            self._attr_longitude = state.attributes.get(ATTR_LONGITUDE)

        self._handle_coordinator_update()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        fix = _gps_fix(self.device_data)
        if fix is None:
            return

        self._attr_latitude, self._attr_longitude = fix
        self.async_write_ha_state()

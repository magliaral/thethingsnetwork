"""The Things Network downlink button platform.

Zero-config: the TTN payload decoder announces the downlink switches a device
accepts via a `_downlink` object in the decoded payload (flattened by
ttn_client to `_downlink_<field>_fport` / `_downlink_<field>_name` values).
For every announced switch this platform creates an On and an Off button that
schedule a confirmed downlink through the TTN application API. No HA-side
configuration is required - the decoder is the single source of truth, exactly
like the `_sensor_attr` metadata on the sensor side.

Class A note: the command reaches the device only in the receive window after
its NEXT uplink; the actual switch state comes back via the echo field in the
following uplink. `confirmed` downlinks are retransmitted by TTN until the
device acknowledges, so a lost radio window heals without any HA-side retry.
"""

from __future__ import annotations

import logging
from typing import Final

from ttn_client import TTNSensorValue

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_APP_ID,
    DOMAIN,
    DOWNLINK_ATTR_BIT,
    DOWNLINK_ATTR_FPORT,
    DOWNLINK_ATTR_NAME,
    DOWNLINK_PREFIX,
)
from .coordinator import TTNCoordinator
from .entity import TTNDeviceEntity

_LOGGER = logging.getLogger(__name__)

_UNIQUE_ID_INFIX: Final = "_downlink_"
_DOWNLINK_ATTRS: Final = (DOWNLINK_ATTR_FPORT, DOWNLINK_ATTR_NAME, DOWNLINK_ATTR_BIT)


def _downlink_switches(device_uplinks: dict) -> dict[str, dict[str, str]]:
    """Extract the announced downlink switches from a device's uplink fields.

    Example input fields:
        _downlink_standheizung_fport = 12
        _downlink_standheizung_name  = "Standheizung"

    Returns:
        {"standheizung": {"fport": "12", "name": "Standheizung"}}
    """

    switches: dict[str, dict[str, str]] = {}

    for field_id, ttn_value in device_uplinks.items():
        if not field_id.startswith(DOWNLINK_PREFIX):
            continue
        if not isinstance(ttn_value, TTNSensorValue):
            continue

        remainder = field_id[len(DOWNLINK_PREFIX) :]
        for attr_key in _DOWNLINK_ATTRS:
            if not remainder.endswith(f"_{attr_key}"):
                continue
            switch_field = remainder[: -(len(attr_key) + 1)]
            if switch_field:
                switches.setdefault(switch_field, {})[attr_key] = str(ttn_value.value)
            break

    return switches


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up TTN downlink buttons from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    app_id = entry.data[CONF_APP_ID]

    # (device_id, switch_field) pairs that already have their button pair
    buttons: set[tuple[str, str]] = set()

    # Devices that have been quiet for longer than the coordinator's backfill
    # window keep their buttons across restarts: recreate them from the entity
    # registry. fport/name resolve lazily from coordinator data, so a button
    # restored this way becomes actionable with the device's next uplink.
    restored: list[TtnDownlinkButton] = []
    for registry_entry in er.async_entries_for_config_entry(
        er.async_get(hass), entry.entry_id
    ):
        if registry_entry.domain != Platform.BUTTON:
            continue
        unique_id = registry_entry.unique_id
        if not unique_id.endswith("_on") and not unique_id.endswith("_off"):
            continue
        base, _, state = unique_id.rpartition("_")
        if _UNIQUE_ID_INFIX not in base:
            continue
        device_id, _, switch_field = base.rpartition(_UNIQUE_ID_INFIX)
        if not device_id or not switch_field:
            continue
        if (device_id, switch_field) in buttons:
            continue
        buttons.add((device_id, switch_field))
        restored += [
            TtnDownlinkButton(coordinator, app_id, device_id, switch_field, turn_on)
            for turn_on in (True, False)
        ]
    if restored:
        async_add_entities(restored)

    def _async_measurement_listener() -> None:
        """Create button pairs for newly announced downlink switches."""
        new_entities: list[TtnDownlinkButton] = []

        for device_id, device_uplinks in coordinator.data.items():
            for switch_field in _downlink_switches(device_uplinks):
                if (device_id, switch_field) in buttons:
                    continue
                buttons.add((device_id, switch_field))
                new_entities += [
                    TtnDownlinkButton(
                        coordinator, app_id, device_id, switch_field, turn_on
                    )
                    for turn_on in (True, False)
                ]

        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_async_measurement_listener))
    _async_measurement_listener()


class TtnDownlinkButton(TTNDeviceEntity, ButtonEntity):
    """Schedules a confirmed TTN downlink that turns one device switch on/off."""

    def __init__(
        self,
        coordinator: TTNCoordinator,
        app_id: str,
        device_id: str,
        switch_field: str,
        turn_on: bool,
    ) -> None:
        """Initialize the downlink button."""
        super().__init__(
            coordinator,
            app_id,
            device_id,
            f"downlink_{switch_field}_{'on' if turn_on else 'off'}",
        )

        self._switch_field = switch_field
        self._turn_on = turn_on
        self._attr_translation_key = "downlink_on" if turn_on else "downlink_off"
        self._attr_icon = "mdi:power" if turn_on else "mdi:power-off"

    def _switch_meta(self, key: str) -> str | None:
        """Return the announced metadata value for this switch, or None."""
        return _downlink_switches(self.device_data).get(self._switch_field, {}).get(key)

    @property
    def translation_placeholders(self) -> dict[str, str]:
        """Resolve the display name from the latest announced metadata."""
        name = self._switch_meta(DOWNLINK_ATTR_NAME)
        return {"name": name if name else self._switch_field.capitalize()}

    async def async_press(self) -> None:
        """Schedule the confirmed downlink."""
        try:
            fport = int(self._switch_meta(DOWNLINK_ATTR_FPORT) or "")
        except ValueError:
            # Restored button without an uplink since HA started: without the
            # announced fPort a command could reach the wrong port - refuse
            # honestly instead of guessing.
            raise HomeAssistantError(
                f"No downlink metadata received yet for {self._device_id}/"
                f"{self._switch_field} - waiting for the device's next uplink"
            ) from None

        try:
            bit = int(self._switch_meta(DOWNLINK_ATTR_BIT) or "")
        except ValueError:
            bit = None

        if bit is not None:
            # Encode the mask/values wire format locally and schedule raw
            # bytes - no dependency on the TTN downlink payload formatter.
            pair, j = divmod(bit, 8)
            frame = bytearray(2 * (pair + 1))
            frame[2 * pair] |= 1 << j
            if self._turn_on:
                frame[2 * pair + 1] |= 1 << j
            await self.coordinator.async_push_downlink(
                self._device_id, fport, raw=bytes(frame)
            )
        else:
            # Uplink decoder does not announce the bit yet: let the TTN
            # downlink formatter encode the JSON command.
            await self.coordinator.async_push_downlink(
                self._device_id, fport, decoded={self._switch_field: self._turn_on}
            )

"""The Things Network's integration constants."""

from homeassistant.const import Platform

DOMAIN = "thethingsnetwork"
TTN_API_HOST = "eu1.cloud.thethings.network"

PLATFORMS = [Platform.BUTTON, Platform.DEVICE_TRACKER, Platform.SENSOR]

CONF_APP_ID = "app_id"

POLLING_PERIOD_S = 60

# Zero-config downlink discovery. The TTN payload decoder announces the
# switches a device accepts via a `_downlink` object in the decoded payload:
#   _downlink: { standheizung: { fport: 12, name: "Standheizung" } }
# ttn_client flattens that to TTNSensorValue fields named
# `_downlink_<field>_fport` / `_downlink_<field>_name`, which the button
# platform turns into On/Off button entities - no HA-side configuration.
DOWNLINK_PREFIX = "_downlink_"
DOWNLINK_ATTR_FPORT = "fport"
DOWNLINK_ATTR_NAME = "name"

# Flat GPS fields emitted by the decoder. Consumed by the device_tracker platform,
# so the sensor platform must not turn them into entities of their own.
FIELD_LATITUDE = "latitude"
FIELD_LONGITUDE = "longitude"
GPS_FIELDS = frozenset({FIELD_LATITUDE, FIELD_LONGITUDE})

# Synthetic field keys for the device-wide entities. The leading underscore cannot
# collide with a decoder field that has an entity, since the sensor platform skips
# every field starting with "_" - so existing unique_ids stay untouched.
KEY_FCNT = "_ttn_f_cnt"
KEY_LAST_SEEN = "_ttn_last_seen"
KEY_TRACKER = "_ttn_location"

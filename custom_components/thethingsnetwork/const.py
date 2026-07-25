"""The Things Network's integration constants."""

from homeassistant.const import Platform

DOMAIN = "thethingsnetwork"
TTN_API_HOST = "eu1.cloud.thethings.network"

PLATFORMS = [Platform.DEVICE_TRACKER, Platform.SENSOR]

CONF_APP_ID = "app_id"

POLLING_PERIOD_S = 60

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

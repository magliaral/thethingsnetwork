# The Things Network — Home Assistant Integration

[![HACS Custom][hacs-badge]][hacs]
[![Release][release-badge]][releases]

A custom Home Assistant integration for [The Things Network][ttn] (TTN) v3.
This is an extended fork of the Home Assistant core `thethingsnetwork`
integration (originally by [@angelnu][angelnu]).

**Design principle of this fork: the TTN payload decoder is the single source
of truth.** Everything Home Assistant needs to know about a device — entity
metadata, GPS capability, and which downlink switches it accepts — is declared
in the application's payload formatter (`decodeUplink`). No YAML, no options
flows, no per-entity customization in Home Assistant.

## Differences to the upstream core integration

| Feature | Core integration | This fork |
|---|---|---|
| Sensor entities per decoded field | ✓ | ✓ |
| **HA metadata from the decoder** (`_sensor_attr`) | — | unit, device_class, state_class, entity_category, display precision, friendly name |
| **GPS device tracker** (`latitude`/`longitude`) | — | ✓ (with fix validation, restore, no "Null Island") |
| **Downlink buttons from the decoder** (`_downlink`) | — | auto-created On/Off buttons, confirmed downlinks, queue merge (multi-switch safe) |
| Per-device diagnostics (FCnt, last seen) | — | ✓ (restored across restarts) |
| Quiet-device restore from the entity registry | — | ✓ (devices silent longer than the backfill window keep their entities) |
| German translations | — | ✓ |

### Decoder-defined entity metadata (`_sensor_attr`)

The decoder annotates any uplink field with Home Assistant metadata by
returning a `_sensor_attr` object in the decoded payload:

```js
data._sensor_attr = {
  batteryVoltage: {
    unit: "V",
    device_class: "voltage",
    state_class: "measurement",
    suggested_display_precision: "1",
    friendly_name: "Batteriespannung"
  },
  batteryAlarm: {
    entity_category: "diagnostic",
    friendly_name: "Batterie Alarm"
  }
};
```

Supported keys: `unit`, `device_class`, `state_class`, `entity_category`,
`suggested_display_precision`, `friendly_name`. Invalid values are logged and
ignored. The sensor entities pick these up on creation — change the decoder,
and every Home Assistant instance consuming the application follows.

### Decoder-announced downlink buttons (`_downlink`)

Devices that accept switch commands announce them in the decoded payload:

```js
data._downlink = {
  standheizung: { fport: 12, bit: 0, name: "Standheizung" }
};
```

For every announced switch the integration automatically creates **two button
entities** on the TTN device — localized as "Standheizung Ein" / "Standheizung
Aus" (German) or "… On" / "… Off" (English). Pressing a button replaces the
device's TTN downlink queue with **one confirmed downlink** (`down/replace`).
With `bit` announced, the integration encodes the mask/values wire format
itself and schedules raw `frm_payload` — no runtime dependency on the TTN
downlink payload formatter. Without `bit` it falls back to scheduling
`decoded_payload: {"standheizung": true}` for the application's
`encodeDownlink` to translate.

Before replacing, the integration reads the pending queue and **merges** any
commands still waiting on the same fPort bit-wise into the new frame (the new
command wins on overlapping bits). Commands for *different* switches issued
within one uplink interval therefore do not overwrite each other, while per
switch the latest command still wins — the queue always holds exactly one
combined downlink. Reading the queue is best effort: if it fails, the command
is scheduled unmerged (the pre-1.3.0 behavior). Queue entries on other fPorts
or with only a `decoded_payload` are dropped by the replace, as before.

Notes:

- **Class A latency:** the command reaches the device only in the receive
  window after its *next* uplink; the switched state is reported back via the
  device's echo field in the following uplink. Two explicit buttons (instead
  of an optimistic HA switch) are deliberate — they are honest about this
  asynchronicity.
- **Confirmed:** TTN retransmits the downlink after every uplink until the
  device acknowledges — lost radio windows heal without any HA-side retry.
- **API key right:** scheduling downlinks requires the application API key to
  hold *"write downlink application traffic"* in addition to the storage read
  right. Re-enter the key via the integration's re-auth flow after extending
  it. Missing rights surface as a clear error when a button is pressed.

### GPS device tracker

Decoded `latitude`/`longitude` fields feed a `device_tracker` entity (map
marker) instead of becoming sensors. All-zero fixes are discarded on the
decoder side, incomplete or non-numeric fixes on the HA side; the last
position is restored across restarts.

### Per-device diagnostics

Every TTN device gets an uplink frame counter (`FCnt`) and a last-seen
timestamp entity, both restored across Home Assistant restarts even when the
device has been quiet longer than the backfill window.

### Decoder contract reference

The uplink/downlink payload formatter contract (including `_sensor_attr`,
`_downlink`, GPS handling and a mask/values downlink wire format for ESPHome
relays) is documented in the [esphome-lorabridge][decoder] README — the
companion project that turns an ESP32 into a LoRaWAN sensor bridge with relay
control. The formatters themselves are per-application deployment config and
live in the TTN console, not in a repository.

## Installation

### Via HACS (recommended)

1. In HACS, open the menu (⋮) → **Custom repositories**.
2. Add `https://github.com/magliaral/thethingsnetwork` as an **Integration**.
3. Install **The Things Network**, then restart Home Assistant.

### Manual

Copy `custom_components/thethingsnetwork/` into your Home Assistant
`config/custom_components/` directory and restart Home Assistant.

## Configuration

Add the integration via **Settings → Devices & Services → Add Integration →
The Things Network**. You will need:

- **Host** — e.g. `eu1.cloud.thethings.network`
- **Application ID**
- **API key** — read access to stored uplinks; add *"write downlink
  application traffic"* if you use downlink buttons

See the [TTN documentation][ttn-docs] for how to create an API key.

## Development

Releases follow [semantic versioning][semver] (`vMAJOR.MINOR.PATCH`) and are
created automatically by the [release workflow](.github/workflows/release.yml).
`main` is protected (PR-only):

- **`dev`** — the working branch. Every push with a release-relevant
  [conventional commit](https://www.conventionalcommits.org/) (`feat:` =
  minor, `fix:`/`refactor:`/`chore:` = patch, `!`/`BREAKING CHANGE` = major)
  bumps the version in `manifest.json` automatically and publishes a
  `v<x.y.z>-beta.<n>` prerelease; old betas are cleaned up automatically.
- **`main`** — merge a pull request from `dev`: the workflow tags the stable
  `v<version>` (the beta suffix is stripped), builds the HACS zip and
  publishes the GitHub release. Do **not** bump versions or tag manually.

Update [`CHANGELOG.md`](CHANGELOG.md) as part of the feature commits on
`dev`.

Every push and pull request also runs the
[validation workflow](.github/workflows/validate.yml) (manifest, translations,
Python syntax, required files).

## Credits

Based on the Home Assistant core integration by [@angelnu][angelnu] and
contributors. Licensed under [Apache 2.0](LICENSE).

[ttn]: https://www.thethingsnetwork.org/
[ttn-docs]: https://www.thethingsindustries.com/docs/integrations/storage/
[angelnu]: https://github.com/angelnu
[decoder]: https://github.com/magliaral/esphome-lorabridge#ttn-payload-decoder
[hacs]: https://hacs.xyz/
[semver]: https://semver.org/
[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[release-badge]: https://img.shields.io/github/v/release/magliaral/thethingsnetwork
[releases]: https://github.com/magliaral/thethingsnetwork/releases

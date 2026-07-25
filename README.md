# The Things Network — Home Assistant Integration

[![HACS Custom][hacs-badge]][hacs]
[![Release][release-badge]][releases]

A custom Home Assistant integration for [The Things Network][ttn] (TTN) v3.
This is an extended fork of the Home Assistant core `thethingsnetwork` integration
(originally by [@angelnu][angelnu]), with additional support for **GPS device
tracking** and **device-wide diagnostic entities**.

## Features

- Connects to a TTN v3 application via the TTN Storage API (cloud polling, 60 s).
- Automatically creates **sensor** entities for every decoded uplink field.
- **Device tracker** with GPS fix support (`latitude` / `longitude` decoder fields).
- Synthetic per-device diagnostic entities:
  - `_ttn_f_cnt` — uplink frame counter
  - `_ttn_last_seen` — timestamp of the last uplink
  - `_ttn_location` — GPS location tracker
- Config flow with re-auth and reconfigure (initial fetch period) support.

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
- **API key** (with read access to stored uplinks)

See the [TTN documentation][ttn-docs] for how to create an API key.

## Development

The `main` branch is the development branch. Releases are tagged with
[semantic versioning][semver] (`vMAJOR.MINOR.PATCH`), matching the `version`
field in [`manifest.json`](custom_components/thethingsnetwork/manifest.json).

To cut a release:

1. Bump `version` in `manifest.json`.
2. Update [`CHANGELOG.md`](CHANGELOG.md).
3. Commit, then tag: `git tag -a vX.Y.Z -m "vX.Y.Z" && git push --tags`.

## Credits

Based on the Home Assistant core integration by [@angelnu][angelnu] and
contributors. Licensed under [Apache 2.0](LICENSE).

[ttn]: https://www.thethingsnetwork.org/
[ttn-docs]: https://www.thethingsindustries.com/docs/integrations/storage/
[angelnu]: https://github.com/angelnu
[hacs]: https://hacs.xyz/
[semver]: https://semver.org/
[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[release-badge]: https://img.shields.io/github/v/release/magliaral/thethingsnetwork
[releases]: https://github.com/magliaral/thethingsnetwork/releases

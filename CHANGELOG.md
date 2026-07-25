# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [1.2.1] - 2026-07-25

### Fixed
- Pressing a downlink button raised `NameError: name 'field' is not defined`
  after the downlink was already scheduled successfully — the success log line
  still referenced the pre-1.2.0 function signature.
- Downlink buttons cache the announced metadata (`fport`/`bit`/`name`) instead
  of reading it live from the coordinator, which only carries uplinks newer
  than its last poll — presses between uplinks no longer fail with
  "No downlink metadata received yet".

## [1.2.0] - 2026-07-25

### Changed
- Downlink buttons now encode the mask/values wire format **locally** and
  schedule raw `frm_payload` when the uplink decoder announces the downlink
  `bit` (in addition to `fport`/`name`) — no runtime dependency on the TTN
  downlink payload formatter anymore. Decoders without a `bit` announcement
  fall back to the previous `decoded_payload` path.

## [1.1.0] - 2026-07-25

### Added
- **Downlink buttons** (`button` platform): the TTN payload decoder announces
  accepted switch commands via a `_downlink` object in the decoded payload
  (`{ standheizung: { fport: 12, name: "Standheizung" } }`); the integration
  automatically creates localized On/Off button entities per switch — no
  HA-side configuration. Pressing a button replaces the device's downlink
  queue with one **confirmed** downlink via the TTN application API
  (`down/replace`, JSON `decoded_payload` encoded by the application's
  downlink payload formatter). Requires the API key right
  *"write downlink application traffic"*.
- Buttons are restored from the entity registry across restarts; fPort and
  display name resolve from the latest announced metadata.
- German translations (`translations/de.json`).
- GitHub workflows: automated releases (stable from `main` via the manifest
  version, `-beta` prereleases from `dev`) and integration validation.

### Changed
- README rewritten around the fork's design principle (decoder as the single
  source of truth) with a feature comparison to the upstream core integration
  and documentation of the `_sensor_attr` metadata contract.

## [1.0.0] - 2026-07-25

### Added
- Initial release as a standalone HACS custom integration.
- GPS `device_tracker` platform with location-fix handling.
- Synthetic per-device diagnostic entities: uplink frame counter
  (`_ttn_f_cnt`), last-seen timestamp (`_ttn_last_seen`) and location
  tracker (`_ttn_location`).

### Changed
- Forked from the Home Assistant core `thethingsnetwork` integration;
  documentation and issue tracker now point to this repository.

[1.2.1]: https://github.com/magliaral/thethingsnetwork/releases/tag/v1.2.1
[1.2.0]: https://github.com/magliaral/thethingsnetwork/releases/tag/v1.2.0
[1.1.0]: https://github.com/magliaral/thethingsnetwork/releases/tag/v1.1.0
[1.0.0]: https://github.com/magliaral/thethingsnetwork/releases/tag/v1.0.0

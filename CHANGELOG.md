# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

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

[1.0.0]: https://github.com/magliaral/thethingsnetwork/releases/tag/v1.0.0

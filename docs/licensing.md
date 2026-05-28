# Licensing

BusierBox's own source code, scripts, tests, and project documentation are
licensed under GPL-2.0-or-later unless a file states a different license.

The top-level `LICENSE.busierbox` file carries the explicit BusierBox project
grant and SPDX expression. The top-level `LICENSE` file contains the GNU
General Public License version 2 text. Because BusierBox is GPL-2.0-or-later,
recipients may use BusierBox's own code under GPLv2 or any later GPL version.
When BusierBox is distributed together with GPLv2-only components, GPLv2 is the
compatible choice for that combined artifact.

The top-level `NOTICE` file repeats the repository-level license declaration in
a short form for release bundles, package inventories, and repository scanners.
`manifests/license-policy.json` is the machine-readable form of the same policy,
and `scripts/check-licensing` validates the policy against the project grant,
pinned source metadata, and bundled notice files. This document is an
engineering license inventory, not legal advice.

## Third-party components

BusierBox integrates upstream software instead of importing BusyBox code into
the supervisor:

| Component | How BusierBox uses it | Recorded license | Compatibility note |
| --- | --- | --- | --- |
| BusyBox | Built or staged as `payload/bin/busybox`; BusierBox dispatches standard applets to it. | GPL-2.0 | Compatible with BusierBox under GPLv2 terms. BusierBox is not a BusyBox fork. |
| Buildroot | Downloaded or unpacked as a build system for target payloads and toolchains. | GPL-2.0-or-later with per-file/package exceptions | Compatible for project/build-system use. Buildroot package recipes can fetch software under many licenses; generated payloads still carry the licenses of their selected packages. |
| doom-ascii | Optional Buildroot payload engine for the `doom` runtime. | GPL-2.0-or-later | Compatible with BusierBox GPL licensing. Game WAD data is user-provided and is not bundled by BusierBox. |
| miniz | Vendored inflate/archive helper in `third_party/miniz`. | MIT OR Unlicense-style notices | Permissive terms are compatible with GPL distribution. |

Pinned downloadable source metadata lives in `manifests/sources.lock.json`.
Machine-readable project/component compatibility policy lives in
`manifests/license-policy.json`.
The BusyBox source tree is tracked as the `third_party/busybox` submodule.
Vendored third-party notices live under `third_party/` and `LICENSES/`.

## GPL compatibility summary

The current default integrated stack is compatible with BusierBox's GPL license
posture:

- GPL components such as BusyBox and doom-ascii can be distributed together
  with BusierBox under GPLv2-compatible terms.
- Buildroot is used to build payloads; it does not make every selected payload
  package GPL. Each selected package keeps its own license and notice
  requirements.
- Permissive components such as miniz can be combined with GPL-licensed
  BusierBox code as long as their notices are preserved.
- User-provided files, including Doom `.wad` data passed through
  `BB_DOOM_WAD_PATH`, are not downloaded or bundled by BusierBox and must be
  supplied under terms the user is allowed to use.

## Artifact guidance

BusierBox release artifacts should preserve source availability and license
notices for included components:

- Keep `manifests/sources.lock.json` current for downloaded source archives;
  release bundles include it as both `sources.lock.json` and
  `manifests/sources.lock.json`.
- Keep `LICENSE.busierbox`, `LICENSE`, and `NOTICE` in release bundles.
- Keep third-party license files with vendored source snippets.
- Do not add a network-fetched component without pinned version, URL, SHA-256,
  filename, license, and homepage metadata.
- Treat optional Buildroot packages as separately licensed payload components;
  their package licenses do not change BusierBox's own license.

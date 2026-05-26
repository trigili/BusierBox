# Licensing

BusierBox's own source code, scripts, tests, and project documentation are
licensed under GPL-2.0-or-later unless a file states a different license.

The top-level `LICENSE` file contains the GNU General Public License version 2.
Because BusierBox is GPL-2.0-or-later, recipients may use BusierBox's own code
under GPLv2 or any later GPL version. When BusierBox is distributed together
with GPLv2-only components, GPLv2 is the compatible choice for that combined
artifact.

## Third-party components

BusierBox integrates upstream software instead of importing BusyBox code into
the supervisor:

| Component | How BusierBox uses it | Recorded license | Compatibility note |
| --- | --- | --- | --- |
| BusyBox | Built or staged as `payload/bin/busybox`; BusierBox dispatches standard applets to it. | GPL-2.0 | Compatible with BusierBox under GPLv2 terms. BusierBox is not a BusyBox fork. |
| Buildroot | Downloaded or unpacked as a build system for target payloads and toolchains. | GPL-2.0-or-later with per-file/package exceptions | Compatible for project/build-system use. Generated payloads still carry the licenses of their selected packages. |
| doom-ascii | Optional Buildroot payload engine for the `doom` runtime. | GPL-2.0-or-later | Compatible with BusierBox GPL licensing. Game WAD data is user-provided and is not bundled by BusierBox. |
| miniz | Vendored inflate/archive helper in `third_party/miniz`. | Unlicense/public-domain-style notice | Permissive/public-domain-style terms are compatible with GPL distribution. |

Pinned downloadable source metadata lives in `manifests/sources.lock.json`.
Vendored third-party notices live under `third_party/` and `LICENSES/`.

## Artifact guidance

BusierBox release artifacts should preserve source availability and license
notices for included components:

- Keep `manifests/sources.lock.json` current for downloaded source archives.
- Keep third-party license files with vendored source snippets.
- Do not add a network-fetched component without pinned version, URL, SHA-256,
  filename, license, and homepage metadata.
- Treat optional Buildroot packages as separately licensed payload components;
  their package licenses do not change BusierBox's own license.

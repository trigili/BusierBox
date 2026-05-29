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
and `make check-licensing` validates the policy against the project grant,
pinned source metadata, explicit GPLv2 compatibility flags, component
distribution obligations, and bundled notice files. This document is an
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
`manifests/license-policy.json`. Every downloadable source lock entry must have
a matching compatibility-policy component before the licensing check passes.
The BusyBox source tree is tracked as the `third_party/busybox` submodule.
Repository-maintained third-party notice summaries for named integrated
components live under `LICENSES/`; vendored upstream notices remain under
`third_party/`.

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

So the repository can say "BusierBox is GPL-licensed" for BusierBox-maintained
code, and GPL is OK for the whole current default stack as a GPLv2-compatible
combined distribution. That is not a blanket relicensing of every possible
future payload: every newly selected Buildroot package still needs its own
license/source/notice review before it is bundled or distributed.

In practical distribution terms, the BusierBox-maintained repository content is
GPL-2.0-or-later. Release artifacts that include BusyBox should be treated as
GPLv2-compatible combined distributions, with source availability and notices
preserved for BusierBox, BusyBox, and every bundled payload component. Buildroot
is a build system and package integrator here; using it is compatible with the
project's GPL posture, but any Buildroot-selected package keeps its own upstream
license and notice/source obligations. User-supplied data, including Doom WAD
files, is not part of BusierBox's license grant and is not bundled by the
project.

## Corresponding source posture

When distributing BusierBox binaries or release bundles, treat corresponding
source as required for BusierBox-maintained code, BusyBox, and every bundled GPL
payload component. The practical source reconstruction set is:

- this repository at the recorded release commit;
- `manifests/sources.lock.json` and the release copies at `sources.lock.json`
  and `manifests/sources.lock.json`;
- pinned downloadable source archives named by that lock file;
- Buildroot-generated source/package manifests when optional payload packages
  are selected;
- vendored notices and license texts under `third_party/`, `LICENSES/`,
  `LICENSE`, `LICENSE.busierbox`, and `NOTICE`.

The license policy records this as `corresponding_source_strategy`. That record
is intentionally conservative: it does not say every future Buildroot package is
GPL-compatible, only that current releases must carry enough pinned source and
notice metadata to audit and satisfy the obligations of whatever was bundled.

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

## Validation

Run `make check-licensing` before adding or changing third-party components.
The check verifies the project GPL declaration, release notice files, pinned
source license metadata, each locked source's compatibility-policy entry,
per-component GPLv2 compatibility flags, distribution obligations, and the
current compatibility inventory.

# Native Intel Wi-Fi and analog audio candidate for Tahoe

This opt-in candidate is for the experimental Intel Tahoe 26.7.1/25G241
installation whose Kepler graphics were patched offline. It does not change
the normal OCLP model builder or automatically enable community drivers.

The physical wireless adapter is Intel 8086:43f0, subsystem 8086:0074. The
adapter and subsystem appear in the fork's AX201 configuration table and in
the released kext's PCI match list. The analog codec is Realtek ALC897. The
working injected layout is **13**, which is present in AppleALC 1.9.8's ALC897
resources. The post-patch IORegistry layout value is not a reason to replace
the working injected layout with 7.

## Pinned upstream components

| Component | Version | Source |
| --- | --- | --- |
| AirportItlwm for Tahoe | 2.4.0 alpha, commit 738d4c6 | [laobamac/itlwm](https://github.com/laobamac/itlwm/releases/tag/v2.4.0-alpha) |
| AppleALC | 1.9.8 Release | [Acidanthera AppleALC](https://github.com/acidanthera/AppleALC/releases/tag/1.9.8) |
| SimpleHDA | 1.0.0 Release | [laobamac/SimpleHDA](https://github.com/laobamac/SimpleHDA/releases/tag/v1.0.0) |
| AppleHDA HAL | Original Apple 600.2, packaged with SimpleHDA | [SimpleHDA provenance](https://github.com/laobamac/SimpleHDA/blob/main/NOTICE.md) |

Downloaded archives matched the SHA-256 digests returned by GitHub:

- AirportItlwm Tahoe Release alpha: `25680aa39ddd79b205141875b261bdcc28bea150d13f27787b3c215555daa00f`.
- AppleALC Release: `d4d36cd2da7863cf7cbfcb0892d45c08457f4f4ddd065a073dd010e46bd63bcb`.
- SimpleHDA Release: `89198256664078c91155d673ee7cebb08134dad1b71d5e34b0aa4ef0d4877f8f`.

The kexts are not Developer ID signed. Archive hashes establish download
integrity, not Apple certification or successful execution. The HAL installer
package is unsigned and is **not executed from Sequoia**. Instead, its original
Apple-signed bundle is extracted and verified with strict codesign checks.
No payload binaries are committed to this fork.

## Source and binary checks

The existing Lilu 1.7.2 satisfies SimpleHDA's declared minimum 1.7.1. The
AppleALC 1.9.8 source declares Tahoe as its maximum supported kernel. The
SimpleHDA source restricts its plugin to Darwin 25 and requires `keepsyms=1`,
which is already present in the working boot arguments.

Mach-O inspection confirmed Intel-compatible payloads. Undefined symbol sets
were checked against the actual Tahoe BootKC/SystemKC exports and the existing
Lilu exports: AirportItlwm (956), AppleALC (382), and SimpleHDA (341) each had no
unmatched imports. The original AppleHDA stack's six executable components also
had no unmatched imports against Tahoe plus their own stack exports. The 15
named kernel symbols used by SimpleHDA were present. Its source AppleHDA files
matched their upstream resource hash manifest.

These are static checks. They do not establish C++ object layout compatibility,
successful runtime hook discovery, association, throughput or sound output.
REA native analysis engines were unavailable; this evidence comes from source
inspection, native `nm`/`otool`/`file` tools and signature checks, not decompilation.

## Configuration isolation

`efi_builder/tahoe_native.py` derives a candidate from the reviewed USB config:

- Keep the original AirportItlwm/legacy wireless stack and AppleALC 1.9.7 on
  Darwin 24. The effective Sequoia entries are compared before and after.
- Disable the Tahoe-only itlwm fallback and select AirportItlwm-Tahoe on 25.x.
  Do not load itlwm and AirportItlwm together.
- Add AppleALC-Tahoe and SimpleHDA only on 25.x, ordered after Lilu. Preserve
  the working layout, device properties, ACPI, boot arguments and security settings.
- Require Tahoe's native IO80211Family/IOSkywalk stack. Reject enabled legacy
  wireless dependencies or blocks affecting these native dependencies on 25.x.
- Exclude all three new bundles from Darwin 26 and later.

`support/native_services_transaction.py` consumes a private, hash-pinned manifest.
It binds the external USB by partition UUID, volume UUID, USB protocol, external
status and EFI partition size. It checks the System/Data identities of the
separate Tahoe installation and refuses the running Data volume as its target.

The transaction verifies source bundle trees, compares the active config with
its reviewed predecessor, validates Lilu's binary hash, backs up the complete
USB EFI and requires absent destination bundles. It installs the HAL solely at
Tahoe Data's `/Library/Audio/Plug-Ins/SimpleHDA/AppleHDAHALPlugIn.bundle`, avoiding
a duplicate AppleHDA restoration. The config is replaced atomically after the
payload copies verify. A full EFI tree comparison permits only the reviewed
config, its backup and three added bundles.

It must preserve the protected Sequoia graphics/audio files, Tahoe graphics
metadata, original BootKC/SystemKC and the patched AuxKC. It neither creates a
System snapshot nor modifies Windows or the firmware default. It leaves USB EFI
read-only. Application failure attempts restoration of the prior config and
removal of newly copied payloads. `--restore` restores the prior config after a
runtime failure; added EFI bundles then remain unreferenced for diagnosis.

The working Sequoia installation has an elided AppleHDA executable: its kext
metadata remains on disk while the driver loads from a kernel collection. The
transaction therefore requires and hashes AppleHDA's Info.plist and Sequoia's
SystemKC, and separately records whether a loose executable exists. Absence is
tracked, not silently ignored; appearance or content changes alter the protected
fingerprint. The first activation attempt stopped at the older, incorrect
loose-executable assumption before any backup or installation writes.

## Validation and runtime status

The custom suite exercises Sequoia isolation, driver conflicts, dependency
ordering, version bounds, native wireless blocks and legacy stack conflicts.
Filesystem cases verify atomic replacement, rejection of an invalid plist,
modified/extra payload files and symlinked bundle contents. These tests use
temporary directories and do not mount or modify a real EFI.

The full repository validation passed, including 60 Darwin payload cases, and
the private candidate passed `ocvalidate`. The USB OpenCore binary version is
not established merely by the validator's reported version.

Actual native Wi-Fi association, speed, audio output and stability require the
next Tahoe boot. The AirportItlwm candidate is alpha: WPA3-only, mandatory PMF,
AWDL/AirDrop and MLO are not supported by its documented implementation, and
Wi-Fi 6 HE is opt-in. The candidate does not enable HE or promise improved speed.

On failure, return through the same USB to Sequoia. A separate native-services
restore wrapper preserves the already working graphics recovery. Do not use the
graphics snapshot rollback merely because Wi-Fi or audio failed. A read-only
diagnostic command on MATE reports loaded drivers, SimpleHDA's runtime state,
interfaces and CoreAudio devices inside Tahoe.

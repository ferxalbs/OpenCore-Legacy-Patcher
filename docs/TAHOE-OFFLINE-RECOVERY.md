# Experimental offline recovery for Tahoe with a Kepler GT 730

The isolated Tahoe 26.7.1 (25G241) installation reached Language Chooser but
displayed a black screen with a cursor. The attempted safe-mode entry did not
provide a usable setup interface. This does not establish whether safe mode was
actually enabled or which component failed to render.

Sequoia 15.7.7 (24G720) remains the recovery environment. Its missing
`/Library/Extensions/GeForce.kext` was restored from the installed OCLP 2.5.1
payload. After reboot, the GT 730 completed a minimal Metal blit with verified
contents. Do not unpatch or replace that working installation to repair Tahoe.

## Why the regular patch command is not used from Sequoia

`PatchSysVolume` resolves `/` as its target and uses the host Data volume,
preferences, policy databases and services. Changing only its mount path or
OS-version constant is insufficient to make it an offline patcher. The new
`sys_patch/offline_tahoe.py` is a separate, explicitly targeted recovery tool;
it does not change the regular GUI or root-patching workflow.

## Evidence and scope

The Kepler patch dictionary is generated for Darwin 25.6, build 25G241, using
the existing GT 730 hardware detection. PatcherSupportPkg 2.0.3 supplies the
25 file operations, including the Tahoe-specific Metal, compiler, ImageIO,
CMPhoto, sandbox and metallib resources. Duplicate operations inherited from
the patch dictionary retain their original order. Five kernel extensions use
OCLP's `OSBundleRequired: Auxiliary` adjustment and `/Library/Extensions`.

A standalone auxiliary kernel collection was successfully built by Sequoia's
`kmutil` in an isolated root layout. Inspection confirmed all five NVIDIA
extensions, the three pre-existing Tahoe auxiliary extensions, and exact links
to Tahoe's BootKC and SystemKC UUIDs. Installed target collections were checked
unchanged after that build. Merely running Tahoe's `kmutil` executable on
Sequoia failed because its newer Swift libraries are unavailable; it is not
used by the recovery tool.

Native binary inspection and actual `kmutil` output establish these facts.
REA's client registration was detected, but no REA tools or native analysis
engines were available in the session. No decompilation or REA-generated
evidence is claimed.

## Application and rollback

The operator prepares a private manifest containing explicit System/Data/group
UUIDs, the original sealed snapshot UUID, payload hashes, symlink targets,
target kernel-collection hashes and the inspected AuxKC bindings. No UUIDs,
serial numbers, payload binaries or policy databases belong in Git.

The standalone tool supports `--check`, `--apply` and `--restore`. The manifest
path is required; it never searches for a destination by name or guesses a disk
number. Applying requires administrator authentication in the user's Terminal.

Before writing, it rejects the running volume group, wrong System/Data members,
unexpected builds, escaping paths, changed resources and mismatched cache UUIDs.
It backs up affected Data files and requires the original Tahoe snapshot. It
mounts only the target System volume, copies and verifies the graphics payload,
installs the prepared AuxKC and invalidates only Tahoe's `KextPolicy` database
family, following OCLP's auxiliary-cache regeneration approach. It preserves
`ExecPolicy` and never kills host services.

It then writes explicit experimental patch metadata and requests a new Tahoe
snapshot with `bless`, without `--setBoot`. Protected Sequoia driver, auxiliary
cache and patch-metadata hashes must remain unchanged. Root-application errors
attempt restoration of the saved Data files and selection of the original
sealed Tahoe snapshot; the receipt reports any rollback failure. `--restore`
provides the same recovery from Sequoia if the subsequent Tahoe boot fails.

The tool does not edit EFI, ACPI, NVRAM, Windows, Wi-Fi configuration or audio.
It does not install auto-patching services. A completed copy and snapshot are
not proof of a successful boot or full GPU compatibility. The next hardware
checks are initial setup, normal boot, Metal, networking, and repeated use.
Audio requires a separate assessment.

## Validation

The custom validation suite includes rejection cases for the running target,
mixed volume groups, duplicate System/Data identities, foreign containers,
path traversal, symlink escape, unsupported operations, incomplete GPU payloads
and cache links to a different OS. These checks do not mount or modify a system.
The regular `--validate` suite also checks supported-model OpenCore generation
and root-patch payload availability. Applying the recovery and booting Tahoe
remain manual hardware checks until recorded otherwise.

The first application stopped before snapshot creation because the original
verifier compared the intermediate Monterey OpenCL files against the final
Big Sur OpenCL merge. The installed library matched the latter exactly. The
Data backup was restored and the original sealed snapshot was selected. The
unsealed base volume retains the file changes; selecting the sealed snapshot
is the boot rollback, not a claim that every base-volume byte was restored.

Verification now computes the final file map in patchset order, including
overwrite semantics. Regression checks cover overlapping files, retained merge
files and overwritten subtrees. All 196 final System files matched the ordered
payload after that correction. A retry is accepted only after a failure receipt
confirms rollback and all saved Data files still match their original backup;
the original backup is reused, not replaced with partially patched files.

## Application result, October 25, 2026

The corrected recovery was applied from Sequoia at 21:07 (America/Lima).
The final payload and AuxKC were independently read back and verified. APFS
reported a new Tahoe snapshot selected with `RootTo`, while retaining the
original sealed snapshot. The metadata contains Kepler, Metal 3802, Tahoe
graphics and both ordered OpenCL groups. The operation did not edit EFI or
request a new firmware default. The protected Sequoia hashes were unchanged,
and its GT 730 still completed the Metal blit with verified data afterward.

The complete validation suite passed again after the ordered-merge correction,
including 60 Darwin payload cases. This records successful offline application,
not successful Tahoe boot. The next test is a **normal** Tahoe-Pruebas boot
through the same USB OpenCore, without Shift. Native root patching should not
be repeated on top of this experimental installation. Initial setup, Metal,
networking and audio remain unverified until checked in Tahoe.

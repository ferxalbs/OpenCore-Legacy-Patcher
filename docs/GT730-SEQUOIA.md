# GT 730 on Sequoia: investigation notes

Status: added validation coverage for the GT 730 PCI ID and Tahoe patch
payloads. Full macOS validation and the Sequoia hardware comparison remain
pending. No driver payload, installed EFI, or running macOS system has changed.

This fork tracks Dortania's development branch. It is not an official OCLP release
or a certified Hackintosh configuration. All saved work lives on the single `main` branch. Individual commits keep the
template correction identifiable if an upstream contribution is considered later.

## Target hardware

| Component | Observed configuration |
| --- | --- |
| CPU | Intel Core i5-10400F, 6 cores / 12 threads |
| RAM | 24 GB |
| GPU | NVIDIA GeForce GT 730, GK208B, PCI `10de:1287`, 2 GB |
| macOS | Sequoia 15.7.7, build `24G720` |
| Reported SMBIOS | `iMac20,1` on a Hackintosh |
| Installed root patches | OCLP 2.5.1 / PatcherSupportPkg 1.9.7 |
| Loaded support kexts | Lilu 1.7.2, WhateverGreen 1.7.1, RestrictEvents 1.1.7 |

The internal SSD EFI (`disk0s1`) was mounted read-only during the follow-up.
It contains `EFI/Boot` and `EFI/Microsoft`, with no `EFI/OC` or OpenCore config.
The fallback `bootx64.efi` is byte-for-byte identical to Microsoft
`bootmgfw.efi`. OpenCore was found on the installer USB EFI (`disk2s1`), at
`/Volumes/EFI/EFI/OC/config.plist`, and inspected read-only. Its SMBIOS, boot
arguments, and loaded kext versions match the running system, pointing to this
USB as the bootloader source. Firmware BootCurrent evidence was not available,
so that origin is not asserted solely from NVRAM. These BSD disk identifiers
can change after a reboot. Do not generate a replacement Hackintosh EFI from
the reported iMac model alone. Serial numbers, UUIDs, personal EFI files,
and complete crash logs are intentionally excluded from these notes.

## Evidence and limits

* A minimal Metal blit completed and its 4096-byte output was verified. This shows
  basic acceleration, not prolonged stability or compatibility with every shader.
* The retained logs contained 120 GPU reset reports dated October 18–24; 117
  identified `mediaanalysisd`, while three did not identify an application.
  Multiple reports can describe the same incident. Errors included graphics
  engine exceptions and MMU faults. These are not proof of physical GPU damage.
* The most recent retained GPU report preceded the audited session's boot.
  No new GPU report appeared during the audit.
* `VTIsHardwareDecodeSupported` returned false for H.264, HEVC, VP9, and AV1.
  This describes the capabilities advertised by this installation; individual
  applications and decoder sessions were not benchmarked.
* There were 47 retained `nsattributedstringagent` crash reports by the end of
  the audit. Most inspected reports failed in CoreFoundation dictionary handling.
  Their cause and relationship to GPU resets remain unproven.
* RAM pressure did not justify a memory upgrade in the observations. APFS had
  approximately 20 GB free and should have more headroom before OS experiments.

## Sequoia stability mitigation

OCLP's default generation disables `mediaanalysisd` for detected Metal 3802
GPUs, including Kepler. The GT 730 fixture now checks that `10de:1287` receives
that default and that its generated config contains `revblock=media`. The
existing setting remains user-controllable. Blocking the service disables face
analysis in Photos and Live Text.

The repository validator also generates the GT 730 Kepler patchset for Sequoia
and Tahoe, checks their OS-specific graphics groups and MetallibSupportPkg
requirements, and includes Darwin 25 in the root-patch payload integrity loop.
Tahoe validation uses synthetic version inputs; it does not establish a Tahoe
boot or runtime result on this machine.

The remaining stability check is a 24-hour Sequoia comparison using a
recoverable EFI: keep the workload and idle periods comparable, verify Metal
acceleration stays active, and compare GPU reset incidents per uptime. If resets
continue, retain the logs and keep investigating; patch generation alone is not
evidence that the crashes are fixed. The `nsattributedstringagent` crashes,
video decoding, and USB mapping remain separate investigations.

No mitigation has been installed in the running EFI. No new driver, Metal
feature level, or hardware video-decoding capability is claimed.

## Validated template correction

The first repository validation failed for `MacBook5,1`: the bundled ocvalidate
identified its schema as OpenCore 1.0.8 and rejected enabled driver entries that
lacked `HideVerbose`. The official OpenCore 1.0.8 sample includes that boolean.
Both bundled OpenCore variants recognize the key, but their version strings use
placeholders; the exact firmware version was not inferred from the validator.

The correction adds `HideVerbose=false` to all 13 entries in
`payloads/Config/config.plist` under `UEFI/Drivers`. Parsed-plist comparison
confirmed that every other value stayed unchanged. No binary was replaced.

Validation with Python 3.11.17 completed with exit code 0:

* 208 generated configurations accepted by ocvalidate.
* 50 Darwin version cases checked for root-patch payload integrity.

The validation results recorded above predate the added Tahoe checks. Even with
those checks passing, synthetic Darwin 25 inputs do not certify a Tahoe boot or
an actual boot on this Hackintosh.

## Recreating the development environment

Use a Python installation from python.org as described in [SOURCE.md](../SOURCE.md).
The audited environment used Python 3.11.17 compiled from official source as a
private macOS framework. Its source archive SHA-256 was:

```text
bfb74ad39efae27cda510f134ab408e00f9992c56851cfc0b1cdb5646da11599
```

The working package versions are preserved in
[`requirements-gt730-sequoia.txt`](../requirements-gt730-sequoia.txt). This is a
device-development snapshot, not a replacement for upstream requirements or a
universal release lockfile. Reassess versions and security updates when resuming.

```sh
python3.11 -m venv .x86_64_venv
.x86_64_venv/bin/python -m pip install -r requirements-gt730-sequoia.txt
.x86_64_venv/bin/python -m pip check
.x86_64_venv/bin/python OpenCore-Patcher-GUI.command --help
.x86_64_venv/bin/python OpenCore-Patcher-GUI.command --validate
```

Resolve platform-dependent packages against the actual target OS: an initial
generic macOS cross-resolution omitted PyObjC dependencies conditional on the
Darwin version. The corrected environment had 172 resolved packages, with 173
installed packages including pip. wxPython 4.3.2, PyObjC 12.2.2, and PyInstaller
6.22.3 passed dependency checks; a hidden wxPython window and OCLP imports worked.

The upstream spec currently requests a universal2 build. An Intel-only custom
build will require an explicit x86_64 target or a complete universal2 dependency
stack. No build-system change or application artifact has been produced for this
fork yet. Do not run packaging steps merely to inspect the source.

The audited source was `8da38565f`, three commits after 3.0.0-rc.3. The installed
stable app remained at 2.5.1. The reviewed Kepler and Metal 3802 changes mainly
target Tahoe; they do not establish a fix for these Sequoia crashes.

## Primary references

* [OCLP: FeatureUnlock and mediaanalysisd](https://dortania.github.io/OpenCore-Legacy-Patcher/FAQ.html#what-are-featureunlock-and-mediaanalysisd)
* [RestrictEvents boot arguments and NVRAM precedence](https://github.com/acidanthera/RestrictEvents#boot-arguments)
* [OpenCore 1.0.8 release](https://github.com/acidanthera/OpenCorePkg/releases/tag/1.0.8)
* [OpenCore 1.0.8 sample configuration](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Docs/Sample.plist)
* [OCLP 3.0.0-rc.3](https://github.com/dortania/OpenCore-Legacy-Patcher/releases/tag/3.0.0-rc.3)
* [Python 3.11.17 source release](https://www.python.org/downloads/release/python-31117/)
* [PyInstaller macOS architecture support](https://pyinstaller.org/en/stable/feature-notes.html#macos-multi-arch-support)

## Follow-up EFI inspection

The installer USB configuration was read in place without editing it:

* `iMac20,1`, RestrictEvents 1.1.7, Lilu 1.7.2, WhateverGreen 1.7.1, and
  AMFIPass 1.4.1 agree with the running system's observations.
* RestrictEvents is enabled, but neither boot arguments nor NVRAM Add entries
  configure `revblock`. Blocking `mediaanalysisd` remains a proposed change.
* All enabled kext executable/plist paths, ACPI tables, and UEFI drivers checked
  were present. This checks references, not binary behavior or ACPI correctness.
* ocvalidate 1.0.8 reported four missing `HideVerbose` keys in the USB's driver
  entries. The USB OpenCore binary recognizes `HideVerbose`, but differs from
  the repository binary. Its version string is a placeholder. Do not infer an
  exact firmware release merely from the validator version. No EFI field was
  changed during the inspection.
* `Vault=Optional`, `SecureBootModel=Disabled`, and `amfi=0x80` with AMFIPass
  loaded were observed. Review the AMFI setup separately before changing it.
* `USBToolBox.kext` and `UTBDefault.kext` are enabled; no dedicated USB-map kext
  was listed. USBToolBox documents UTBDefault as the pre-mapping attachment
  configuration. A proper port map is a separate follow-up, not an established
  cause of the GPU faults. See the
  [USBToolBox workflow](https://github.com/USBToolBox/kext#usage).

A private EFI backup was kept locally outside the repository. Its configuration
contains device identifiers and is not uploaded to this public fork. No runtime
GPU mitigation, EFI installation, or root patching was performed.

## Investigación posterior: NullMoth NVIDIA

El propietario indicó que no utiliza las funciones de Fotos y Live Text
afectadas por `mediaanalysisd`. Esa preferencia queda registrada para la prueba
de mitigación; todavía no se modificó la EFI.

Se revisó NullMoth NVIDIA Driver v2.5.4, commit
`46779055f68208baa5ddfb9b2e9c77ed028e1d59`. Su implementación GSP requiere
Turing o posterior y excluye nuestra GT 730 Kepler. La investigación, sus fuentes
y límites están en [NULLMOTH-NVIDIA-INVESTIGATION.md](NULLMOTH-NVIDIA-INVESTIGATION.md).
No se instalaron componentes ni se trasladaron sus parámetros al arranque.

## Ruta Kepler de OCLP y candidato de estabilidad

Kepler dispone de parches OCLP tanto en Sequoia como en la rama de Tahoe. La
exclusión encontrada en NullMoth corresponde a su implementación GSP, no a
OCLP. La comparación por sistema y la primera receta candidata se conservan en
[KEPLER-OPTIMIZATION-PLAN.md](KEPLER-OPTIMIZATION-PLAN.md). Se preparó una copia
privada de EFI con `revblock=auto,media` y cuatro claves HideVerbose faltantes;
ocvalidate 1.0.8 la aprobó. No se instaló ni arrancó esa copia.

## Revisión web del soporte Sequoia (2026-10-25)

Apple muestra macOS Sequoia 15.8.1 como la actualización más reciente de la
rama 15.x. Su aviso de seguridad indica que se publicó el 28 de septiembre de
2026 e incluye una corrección de CoreGraphics. Esto justifica evaluar una
actualización por seguridad; no demuestra que 15.8.1 corrija los reinicios de
la GT 730 ni que esta EFI concreta ya haya sido probada con esa versión.

La guía de modelos de OCLP está dirigida a Macs Intel enumerados por el
proyecto. El equipo descrito aquí usa un PC i5-10400F con SMBIOS de Mac, por lo
que sus resultados son experimentales y no tienen garantía ni soporte upstream
para ese hardware. La rama de este repositorio también contiene desarrollo para
Tahoe; no debe tratarse como una versión certificada para instalar en el equipo.

La mitigación de `mediaanalysisd` ya existe en el código: [defaults.py](../opencore_legacy_patcher/support/defaults.py)
la activa al detectar GPUs Ivy Bridge, Haswell o Kepler; [misc.py](../opencore_legacy_patcher/efi_builder/misc.py)
la traduce a `revblock=media`; y la configuración permite desactivarla. OCLP
documenta que deshabilitar ese servicio es su opción predeterminada para GPUs
Metal 3802 por estabilidad, a costa de Face Detection en Fotos y Live Text. La
validación del repo comprueba el valor predeterminado y su override, pero no
puede confirmar estabilidad en ejecución. Por eso el bloqueo es un candidato
medible, no una solución demostrada a los resets de GPU.

La EFI USB inspeccionada en este seguimiento no llevaba `revblock=media`. El
perfil candidato que sí lo incluye permanece sin instalar ni arrancar; por
tanto, la mitigación todavía no está activa en el sistema observado.

Antes de una prueba de actualización, conserva una EFI conocida que arranque y
una copia de seguridad recuperable. Desactiva la descarga automática de
actualizaciones y revisa primero la compatibilidad del código y sus payloads
con la versión exacta. Las guías de OCLP recomiendan actualizar la aplicación y
OpenCore antes de una actualización menor y volver a instalar los parches de
volumen al terminar; algunos sistemas Sequoia requieren red para descargar
MetallibSupportPkg al reaplicar los parches. La documentación de Legacy Metal
también registra que Software Update puede quedarse girando en NVIDIA Kepler y
remite a actualizar desde línea de comandos. Esas instrucciones describen OCLP
en Macs compatibles; en este Hackintosh no garantizan un procedimiento seguro.

La validación local de Kepler compara Sequoia 15.7.7 con Tahoe sintético. No
incluye todavía una prueba de selección de parches para Sequoia 15.8.1 y ninguna
validación del repositorio equivale a arrancar o probar la GPU. Para el sistema
real, compara periodos equivalentes con la EFI candidata: incidentes GPU por
tiempo de actividad, carga de trabajo, reposo, continuidad de WindowServer y
una prueba Metal con salida verificada. Mantén separadas las pruebas de
decodificación de vídeo y los cierres de `nsattributedstringagent`.

### Fuentes

* [Apple: novedades de las actualizaciones de Sequoia 15](https://support.apple.com/en-us/120283)
* [Apple: contenido de seguridad de Sequoia 15.8.1](https://support.apple.com/es-la/149229)
* [OCLP: modelos compatibles](https://dortania.github.io/OpenCore-Legacy-Patcher/MODELS.html)
* [OCLP: FeatureUnlock y mediaanalysisd](https://dortania.github.io/OpenCore-Legacy-Patcher/FAQ.html#what-are-featureunlock-and-mediaanalysisd)
* [OCLP: actualización de OpenCore y parches](https://dortania.github.io/OpenCore-Legacy-Patcher/UPDATE.html)
* [OCLP: problemas gráficos de Legacy Metal, incluido Kepler](https://github.com/dortania/OpenCore-Legacy-Patcher/issues/1008)

## Estado posterior a la instalación de la mitigación

El 25 de octubre de 2026 se instaló y verificó el config candidato en la EFI
USB, conservando los otros 124 archivos y un respaldo del config original.
Se mantienen los parches gráficos de OCLP 2.5.1. El reinicio del mismo día confirmó el argumento efectivo y RestrictEvents
cargado, sin informes GPU nuevos durante la comprobación inicial; véase
[KEPLER-OPTIMIZATION-PLAN.md](KEPLER-OPTIMIZATION-PLAN.md). Las observaciones
anteriores que describen una propuesta sin aplicar corresponden a la auditoría
inicial, antes de esta instalación.

## Comprobación después del reinicio

El 25 de octubre a las 16:09 (America/Lima), el sistema arrancado mostró
`revblock=auto,media` y RestrictEvents 1.1.7 cargado. No se observó ningún
proceso `mediaanalysisd` ni informes `.gpuRestart` nuevos desde ese arranque.
La GT 730 completó la operación Metal con datos verificados; conserva Metal
Mac1 y no anuncia Mac2 ni decodificación de vídeo por hardware en la prueba.
Esto confirma la activación y una operación gráfica básica, pero la estabilidad
durante uso prolongado y reposo sigue pendiente de observación.

"""
validation.py: Validation class for the patcher
"""

import atexit
import copy
import logging
import plistlib
import subprocess

from pathlib import Path

from . import defaults, network_handler

from .. import constants

from ..sys_patch import sys_patch_helpers
from ..efi_builder import build
from ..support import subprocess_wrapper

from ..datasets import (
    example_data,
    model_array,
    os_data
)
from ..sys_patch.patchsets import (
    HardwarePatchsetDetection,
    PatchType,
    DynamicPatchset
)
from ..sys_patch.patchsets.hardware.graphics import nvidia_kepler
from ..detections import device_probe
from .offline_tahoe_validation import validate_offline_tahoe_recovery


class PatcherValidation:
    """
    Validation class for the patcher

    Primarily for Continuous Integration
    """

    def __init__(self, global_constants: constants.Constants, verify_unused_files: bool = False) -> None:
        self.constants: constants.Constants = global_constants
        self.verify_unused_files = verify_unused_files
        self.active_patchset_files = []

        self.constants.validate = True

        self.valid_dumps = [
            example_data.MacBookPro.MacBookPro92_Stock,
            example_data.MacBookPro.MacBookPro111_Stock,
            example_data.MacBookPro.MacBookPro133_Stock,

            example_data.Macmini.Macmini52_Stock,
            example_data.Macmini.Macmini61_Stock,
            example_data.Macmini.Macmini71_Stock,

            example_data.iMac.iMac81_Stock,
            example_data.iMac.iMac112_Stock,
            example_data.iMac.iMac122_Upgraded,
            example_data.iMac.iMac122_Upgraded_Nvidia,
            example_data.iMac.iMac151_Stock,

            example_data.MacPro.MacPro31_Stock,
            example_data.MacPro.MacPro31_Upgrade,
            example_data.MacPro.MacPro31_Modern_AMD,
            example_data.MacPro.MacPro31_Modern_Kepler,
            example_data.MacPro.MacPro31_Modern_GT730,
            example_data.MacPro.MacPro41_Upgrade,
            example_data.MacPro.MacPro41_Modern_AMD,
            example_data.MacPro.MacPro41_51__Flashed_Modern_AMD,
            example_data.MacPro.MacPro41_51_Flashed_NVIDIA_WEB_DRIVERS,
        ]

        self.valid_dumps_native = [
            example_data.iMac.iMac201_Stock,
            example_data.MacBookPro.MacBookPro141_SSD_Upgrade,
        ]

        self._validate_configs()
        self._validate_gt730_stability_config()
        self._validate_gt730_kepler_patchsets()
        validate_offline_tahoe_recovery()
        self._validate_sys_patch()


    def _build_prebuilt(self) -> None:
        """
        Generate a build for each predefined model
        Then validate against ocvalidate
        """

        for model in model_array.SupportedSMBIOS:
            logging.info(f"Validating predefined model: {model}")
            self.constants.custom_model = model
            build.BuildOpenCore(self.constants.custom_model, self.constants)
            result = subprocess.run([self.constants.ocvalidate_path, f"{self.constants.opencore_release_folder}/EFI/OC/config.plist"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if result.returncode != 0:
                logging.info("Error on build!")
                subprocess_wrapper.log(result)
                raise Exception(f"Validation failed for predefined model: {model}")
            else:
                logging.info(f"Validation succeeded for predefined model: {model}")


    def _build_dumps(self) -> None:
        """
        Generate a build for each predefined model
        Then validate against ocvalidate
        """

        for model in self.valid_dumps:
            self.constants.computer = model
            self.constants.custom_model = ""
            logging.info(f"Validating dumped model: {self.constants.computer.real_model}")
            build.BuildOpenCore(self.constants.computer.real_model, self.constants)
            result = subprocess.run([self.constants.ocvalidate_path, f"{self.constants.opencore_release_folder}/EFI/OC/config.plist"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if result.returncode != 0:
                logging.info("Error on build!")
                subprocess_wrapper.log(result)
                raise Exception(f"Validation failed for predefined model: {self.constants.computer.real_model}")
            else:
                logging.info(f"Validation succeeded for predefined model: {self.constants.computer.real_model}")


    def _validate_gt730_stability_config(self) -> None:
        """Validate the GT 730 default mitigation and its user override."""

        validation_constants = copy.copy(self.constants)
        validation_constants.computer = copy.deepcopy(example_data.MacPro.MacPro31_Modern_GT730)
        validation_constants.custom_model = ""

        defaults.GenerateDefaults(
            validation_constants.computer.real_model,
            True,
            validation_constants,
            ignore_settings_file=True
        )
        if validation_constants.disable_mediaanalysisd is not True:
            raise Exception("GT 730 defaults did not disable mediaanalysisd")

        self._validate_gt730_generated_config(validation_constants, expect_media_block=True)

        validation_constants.disable_mediaanalysisd = False
        self._validate_gt730_generated_config(validation_constants, expect_media_block=False)


    def _validate_gt730_generated_config(
        self,
        validation_constants: constants.Constants,
        expect_media_block: bool
    ) -> None:
        """Build and validate a GT 730 config with or without the media block."""

        build.BuildOpenCore(validation_constants.computer.real_model, validation_constants)
        config_path = Path(validation_constants.opencore_release_folder) / "EFI" / "OC" / "config.plist"

        result = subprocess.run(
            [validation_constants.ocvalidate_path, str(config_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        if result.returncode != 0:
            subprocess_wrapper.log(result)
            raise Exception("GT 730 OpenCore configuration failed validation")

        with config_path.open("rb") as config_file:
            config = plistlib.load(config_file)

        restrict_events = config["NVRAM"]["Add"]["4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102"]
        block_args = {
            argument.strip()
            for argument in restrict_events.get("revblock", "").split(",")
            if argument.strip()
        }

        if ("media" in block_args) != expect_media_block:
            raise Exception("GT 730 config does not match the mediaanalysisd setting")
        if "pcie" not in block_args:
            raise Exception("GT 730 config did not preserve the Mac Pro revblock setting")


    def _validate_gt730_kepler_patchsets(self) -> None:
        """Check GT 730 detection and OS-specific Sequoia/Tahoe patch selection."""

        validation_constants = copy.copy(self.constants)
        validation_constants.computer = copy.deepcopy(example_data.MacPro.MacPro31_Modern_GT730)
        gpu = validation_constants.computer.gpus[0]

        if not isinstance(gpu, device_probe.NVIDIA) or gpu.device_id != 0x1287:
            raise Exception("GT 730 validation fixture does not use PCI device 10de:1287")
        if gpu.arch != device_probe.NVIDIA.Archs.Kepler:
            raise Exception("GT 730 PCI device 10de:1287 was not detected as Kepler")

        os_cases = [
            (24, 6, "24G720", "15.7.7", False),
            (25, 0, "25G229", "26.0", True),
        ]

        for xnu_major, xnu_minor, os_build, os_version, is_tahoe in os_cases:
            validation_constants.detected_os_version = os_version
            patchset = nvidia_kepler.NvidiaKepler(
                xnu_major,
                xnu_minor,
                os_build,
                validation_constants
            )

            if patchset.present() is not True:
                raise Exception(f"GT 730 was not detected by the Kepler patchset on Darwin {xnu_major}")

            patches = patchset.patches()
            required_groups = {"Nvidia Kepler", "Metal 3802 Common"}
            required_groups.add("Metal 3802 .metallibs Tahoe" if is_tahoe else "Metal 3802 .metallibs")
            if is_tahoe:
                required_groups.add("Tahoe Graphics")
            if not required_groups.issubset(patches):
                missing_groups = ", ".join(sorted(required_groups.difference(patches)))
                raise Exception(f"GT 730 patchset for Darwin {xnu_major} is missing: {missing_groups}")

            forbidden_groups = (
                {"Metal 3802 .metallibs"}
                if is_tahoe
                else {"Metal 3802 .metallibs Tahoe", "Tahoe Graphics"}
            )
            if forbidden_groups.intersection(patches):
                raise Exception(f"GT 730 patchset for Darwin {xnu_major} contains cross-version graphics patches")

            kepler_overwrite = patches["Nvidia Kepler"][PatchType.OVERWRITE_SYSTEM_VOLUME]
            extensions = kepler_overwrite["/System/Library/Extensions"]
            if extensions.get("GeForce.kext") != "12.0 Beta 6-23.4":
                raise Exception(f"GT 730 patchset for Darwin {xnu_major} selected an unexpected GeForce.kext")
            if extensions.get("GeForceMTLDriver.bundle") != "11.0 Beta 3-22":
                raise Exception(f"GT 730 patchset for Darwin {xnu_major} selected an unexpected Metal driver")

            kepler_merge = patches["Nvidia Kepler"][PatchType.MERGE_SYSTEM_VOLUME]
            system_frameworks = kepler_merge["/System/Library/Frameworks"]
            private_frameworks = kepler_merge["/System/Library/PrivateFrameworks"]
            if is_tahoe:
                sandbox_profiles = kepler_overwrite["/System/Library/Sandbox/Profiles"]
                if not {"ImageIO.framework", "CMPhoto.framework"}.issubset(
                    set(system_frameworks).union(private_frameworks)
                ) or "nsattributedstringagent.sb" not in sandbox_profiles:
                    raise Exception("Tahoe GT 730 patchset is missing Tahoe-specific compatibility files")
                common_merge = patches["Metal 3802 Common"][PatchType.MERGE_SYSTEM_VOLUME]
                common_frameworks = common_merge["/System/Library/Frameworks"]
                common_private_frameworks = common_merge["/System/Library/PrivateFrameworks"]
                if common_frameworks.get("Metal.framework") != "13.2.1-25":
                    raise Exception("Tahoe GT 730 patchset selected an unexpected Metal.framework")
                if common_private_frameworks.get("MTLCompiler.framework") != "13.6-25":
                    raise Exception("Tahoe GT 730 patchset selected an unexpected MTLCompiler.framework")
                if common_private_frameworks.get("GPUCompiler.framework") != "13.2.1-25":
                    raise Exception("Tahoe GT 730 patchset selected an unexpected GPUCompiler.framework")
                if patchset.requires_metallib_support_pkg() is not False:
                    raise Exception("Tahoe GT 730 patchset incorrectly requires MetallibSupportPkg")
            else:
                if {"ImageIO.framework", "CMPhoto.framework"}.intersection(
                    set(system_frameworks).union(private_frameworks)
                ):
                    raise Exception("Sequoia GT 730 patchset contains Tahoe-only framework payloads")
                if "nsattributedstringagent.sb" in kepler_overwrite.get("/System/Library/Sandbox/Profiles", {}):
                    raise Exception("Sequoia GT 730 patchset contains a Tahoe-only sandbox profile")
                if "Metal 3802 Common Extended" not in patches:
                    raise Exception("Sequoia GT 730 patchset is missing the extended Metal 3802 stack")
                extended_merge = patches["Metal 3802 Common Extended"][PatchType.MERGE_SYSTEM_VOLUME]
                extended_private_frameworks = extended_merge["/System/Library/PrivateFrameworks"]
                if extended_private_frameworks.get("MTLCompiler.framework") != "14.2 Beta 1":
                    raise Exception("Sequoia GT 730 patchset selected an unexpected MTLCompiler.framework")
                if extended_private_frameworks.get("GPUCompiler.framework") != "14.2 Beta 1":
                    raise Exception("Sequoia GT 730 patchset selected an unexpected GPUCompiler.framework")
                if patchset.requires_metallib_support_pkg() is not True:
                    raise Exception("Sequoia GT 730 patchset must require MetallibSupportPkg")


    def _validate_root_patch_files(self, major_kernel: int, minor_kernel: int) -> None:
        """
        Validate that all files in the patchset are present in the payload

        Parameters:
            major_kernel (int): Major kernel version
            minor_kernel (int): Minor kernel version
        """

        patch_type_merge_exempt     = ["MechanismPlugins", "ModulePlugins"]
        patch_type_overwrite_exempt = []

        patchset = HardwarePatchsetDetection(self.constants, xnu_major=major_kernel, xnu_minor=minor_kernel, validation=True).patches

        for patch_core in patchset:
            # Check if any unknown PathType is present
            for install_type in patchset[patch_core]:
                if install_type not in PatchType:
                    raise Exception(f"Unknown PatchType: {install_type}")

            for install_type in [PatchType.OVERWRITE_SYSTEM_VOLUME, PatchType.OVERWRITE_DATA_VOLUME, PatchType.MERGE_SYSTEM_VOLUME, PatchType.MERGE_DATA_VOLUME]:
                if install_type in patchset[patch_core]:
                    for install_directory in patchset[patch_core][install_type]:
                        for install_file in patchset[patch_core][install_type][install_directory]:
                            try:
                                if patchset[patch_core][install_type][install_directory][install_file] in DynamicPatchset:
                                    continue
                            except TypeError:
                                pass

                            # Technically there is nothing wrong with using a .framework with OVERWRITE, but it's a good indicator of a mistake
                            if install_type in [PatchType.OVERWRITE_SYSTEM_VOLUME, PatchType.OVERWRITE_DATA_VOLUME]:
                                if install_file.endswith(".framework") and install_file not in patch_type_overwrite_exempt:
                                    raise Exception(f"{install_file} used with {install_type}, are you certain this is correct?")
                            elif install_type in [PatchType.MERGE_SYSTEM_VOLUME, PatchType.MERGE_DATA_VOLUME]:
                                if not install_file.endswith(".framework") and install_file not in patch_type_merge_exempt:
                                    raise Exception(f"{install_file} used with {install_type}, are you certain this is correct?")

                            source_file = str(self.constants.payload_local_binaries_root_path) + "/" + patchset[patch_core][install_type][install_directory][install_file] + install_directory + "/" + install_file
                            if not Path(source_file).exists():
                                logging.info(f"File not found: {source_file}")
                                raise Exception(f"Failed to find {source_file}")
                            if self.verify_unused_files is True:
                                if source_file not in self.active_patchset_files:
                                    self.active_patchset_files.append(source_file)

        logging.info(f"Validating against Darwin {major_kernel}.{minor_kernel}")
        if not sys_patch_helpers.SysPatchHelpers(self.constants).generate_patchset_plist(patchset, f"OpenCore-Legacy-Patcher-{major_kernel}.{minor_kernel}.plist", None, None):
            raise Exception("Failed to generate patchset plist")

        # Remove the plist file after validation
        Path(self.constants.payload_path / f"OpenCore-Legacy-Patcher-{major_kernel}.{minor_kernel}.plist").unlink()


    def _unmount_dmg(self) -> None:
        """
        Unmounts the Universal-Binaries.dmg
        """
        if Path(self.constants.payload_path / Path("Universal-Binaries_overlay")).exists():
            subprocess.run(
                [
                    "/bin/rm", "-f", Path(self.constants.payload_path / Path("Universal-Binaries_overlay"))
                ],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
        if Path(self.constants.payload_path / Path("Universal-Binaries")).exists():
            output = subprocess.run(
                [
                    "/usr/bin/hdiutil", "detach", Path(self.constants.payload_path / Path("Universal-Binaries")),
                    "-force"
                ],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )

            if output.returncode != 0:
                logging.info("Failed to unmount Universal-Binaries.dmg")
                subprocess_wrapper.log(output)

                raise Exception("Failed to unmount Universal-Binaries.dmg")


    def _validate_sys_patch(self) -> None:
        """
        Validates sys_patch modules
        """

        if not Path(self.constants.payload_local_binaries_root_path_dmg).exists():
            dl_obj = network_handler.DownloadObject(f"https://github.com/dortania/PatcherSupportPkg/releases/download/{self.constants.patcher_support_pkg_version}/Universal-Binaries.dmg", self.constants.payload_local_binaries_root_path_dmg)
            dl_obj.download(spawn_thread=False)
            if dl_obj.download_complete is False:
                logging.info("Failed to download Universal-Binaries.dmg")
                raise Exception("Failed to download Universal-Binaries.dmg")

        logging.info("Validating Root Patch File integrity")

        self._unmount_dmg()

        output = subprocess.run(
            [
                "/usr/bin/hdiutil", "attach", "-noverify", f"{self.constants.payload_local_binaries_root_path_dmg}",
                "-mountpoint", Path(self.constants.payload_path / Path("Universal-Binaries")),
                "-nobrowse",
                "-shadow", Path(self.constants.payload_path / Path("Universal-Binaries_overlay")),
                "-passphrase", "password"
            ],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )

        if output.returncode != 0:
            logging.info("Failed to mount Universal-Binaries.dmg")
            subprocess_wrapper.log(output)

            raise Exception("Failed to mount Universal-Binaries.dmg")

        logging.info("Mounted Universal-Binaries.dmg")

        atexit.register(self._unmount_dmg)

        for supported_os in [
            os_data.os_data.big_sur,
            os_data.os_data.monterey,
            os_data.os_data.ventura,
            os_data.os_data.sonoma,
            os_data.os_data.sequoia,
            os_data.os_data.tahoe,
        ]:
            for i in range(0, 10):
                self._validate_root_patch_files(supported_os, i)

        logging.info("Validating SNB Board ID patcher")
        self.constants.computer.reported_board_id = "Mac-7BA5B2DFE22DDD8C"
        sys_patch_helpers.SysPatchHelpers(self.constants).snb_board_id_patch(self.constants.payload_local_binaries_root_path)

        if self.verify_unused_files is True:
            self._find_unused_files()

        # unmount the dmg
        output = subprocess.run(
            [
                "/usr/bin/hdiutil", "detach", Path(self.constants.payload_path / Path("Universal-Binaries")),
                "-force"
            ],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )

        if output.returncode != 0:
            logging.info("Failed to unmount Universal-Binaries.dmg")
            subprocess_wrapper.log(output)

            raise Exception("Failed to unmount Universal-Binaries.dmg")

        subprocess.run(
            [
                "/bin/rm", "-f", Path(self.constants.payload_path / Path("Universal-Binaries_overlay"))
            ],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )


    def _find_unused_files(self) -> None:
        """
        Find PatcherSupportPkg files that are unused by the patcher

        Note this function is extremely slow, so only manually run when needed
        """
        if self.active_patchset_files == []:
            return

        unused_files = []

        for file in Path(self.constants.payload_local_binaries_root_path).rglob("*"):
            if file.is_dir():
                continue

            relative_path = Path(file).relative_to(self.constants.payload_local_binaries_root_path)

            if relative_path.name == ".DS_Store":
                continue

            if str(relative_path) in [".fseventsd/fseventsd-uuid", ".signed"]:
                continue

            is_used = False
            for used_file in self.active_patchset_files:
                used_relative_path = Path(used_file).relative_to(self.constants.payload_local_binaries_root_path)
                if str(relative_path) in str(used_relative_path):
                    is_used = True
                    break
                if str(used_relative_path) in str(relative_path):
                    is_used = True
                    break

            if is_used:
                continue

            unused_files.append(relative_path)

        if len(unused_files) > 0:
            logging.info("Unused files found:")
            for file in unused_files:
                logging.info(f"  {file}")


    def _validate_configs(self) -> None:
        """
        Validates build modules
        """

        # First run is with default settings
        self._build_prebuilt()
        self._build_dumps()

        # Second run, flip all settings
        self.constants.verbose_debug = True
        self.constants.opencore_debug = True
        self.constants.kext_debug = True
        self.constants.kext_variant = "DEBUG"
        self.constants.kext_debug = True
        self.constants.showpicker = False
        self.constants.sip_status = False
        self.constants.secure_status = True
        self.constants.firewire_boot = True
        self.constants.nvme_boot = True
        self.constants.enable_wake_on_wlan = True
        self.constants.disable_tb = True
        self.constants.force_surplus = True
        self.constants.software_demux = True
        self.constants.serial_settings = "Minimal"

        self._build_prebuilt()
        self._build_dumps()

        subprocess.run(["/bin/rm", "-rf", self.constants.build_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

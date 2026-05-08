from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LicenseBuildConfig:
    embedded_enc_key_hex: str = ""
    embedded_mac_key_hex: str = ""
    secret_fingerprint: str = ""


LICENSE_BUILD_CONFIG = LicenseBuildConfig()


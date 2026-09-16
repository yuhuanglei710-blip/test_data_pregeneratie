"""Shared enumerations used by API helpers."""

from enum import Enum


class Platform(Enum):
    web = 1
    android = 2
    ios = 3


class ComplianceStatus(Enum):
    """KYC compliance status."""

    compliance = 1
    noncompliance = 0


# Keep the original misspelled name so existing imports continue to work.
Compliancestatus = ComplianceStatus


class ChannelCode(Enum):
    """Reserved for channel-code values."""


class TimestampMethod(Enum):
    add = 1
    sub = 0

"""Catalogue adapters for SAR providers."""

from sartool.providers.asf import ASFAdapter
from sartool.providers.capella import CapellaAdapter
from sartool.providers.iceye import ICEYEAdapter
from sartool.providers.nisar import NISARAdapter
from sartool.providers.umbra import UmbraAdapter

PROVIDERS = ("asf", "iceye", "capella", "umbra", "nisar")
PRODUCTS = {
    "asf": "sentinel-1-grd",
    "iceye": "iceye-grd",
    "capella": "capella-detected",
    "umbra": "umbra-gec",
    "nisar": "nisar-gcov",
}


def make_adapter(
    provider: str,
) -> ASFAdapter | ICEYEAdapter | CapellaAdapter | UmbraAdapter | NISARAdapter:
    """Create a discovery adapter by public provider name."""
    if provider == "asf":
        return ASFAdapter()
    if provider == "iceye":
        return ICEYEAdapter()
    if provider == "capella":
        return CapellaAdapter()
    if provider == "umbra":
        return UmbraAdapter()
    if provider == "nisar":
        return NISARAdapter()
    raise ValueError(f"unsupported provider: {provider}")

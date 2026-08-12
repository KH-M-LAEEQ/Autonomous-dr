"""SUPPORTING INTERFACE -- PricingSource.

Not one of the five headline interfaces, but freeze it in Week 2 anyway: the
plan introduces it in Week 5 and swaps live APIs in at Week 12, and adding an
interface after the freeze costs you an ADR you do not need to write.

Implemented by: StaticPriceTable (W5), AWSPriceListSource (W12),
AzureRetailPricesSource (W12), GCPBillingSource (W21).
"""

from abc import ABC, abstractmethod


class PricingSource(ABC):
    """Unit prices for cost estimation. Cached; static table is the fallback."""

    name: str

    @abstractmethod
    async def unit_price(self, provider: str, region: str, sku: str) -> float:
        """Price per hour in USD for one SKU in one region."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """False if the live API is unreachable, so the caller can fall back."""
        ...

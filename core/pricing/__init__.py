"""PricingSource implementations. StaticPriceTable (W5) is the fallback every
later source (AWSPriceListSource, AzureRetailPricesSource, GCPBillingSource,
W12/W21) falls back to when its live API is unavailable."""

from core.pricing.static_table import StaticPriceTable

__all__ = ["StaticPriceTable"]

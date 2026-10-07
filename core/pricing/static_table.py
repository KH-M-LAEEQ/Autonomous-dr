"""StaticPriceTable -- Week 5's `PricingSource`.

Implements `core.interfaces.pricing_source.PricingSource`. No network calls,
no region-specific pricing yet: one hourly rate per SKU, the same everywhere.
`AWSPriceListSource` etc. (Week 12) replace this at runtime via config; this
stays registered as the fallback they use when their live API answers
`is_available() == False`.

SKU is the action type's string value (`ActionType`, e.g. "dns_weight_shift")
-- there is no separate catalogue of SKUs yet, so the action type IS the SKU.
"""

from __future__ import annotations

from core.interfaces.pricing_source import PricingSource

#: USD per hour, by SKU (= ActionType value). Deliberately tiny for Tier 1
#: actions -- a DNS weight shift or a reroute is a config change, not a
#: provisioned resource. Mirrors the relative ordering (not the exact
#: numbers) of `core.providers.simulated._STATIC_PRICE_USD`, which prices
#: the same action types for `CloudProvider.estimate_cost`'s simpler use.
_HOURLY_USD: dict[str, float] = {
    "dns_weight_shift": 0.60,
    "traffic_reroute": 0.60,
    "scale_out": 30.00,
    "region_failover": 300.00,
    "cross_cloud_failover": 480.00,
    "dr_promotion": 1200.00,
    "no_op": 0.00,
}
#: Charged for any SKU this table has no entry for, so a new `ActionType`
#: never makes `unit_price` raise -- it is quoted an a "unknown and
#: expensive" placeholder, which fails safe: it trips the budget gate rather
#: than sliding under it for free.
_DEFAULT_HOURLY_USD = 10.00


class StaticPriceTable(PricingSource):
    name = "static_table"

    async def unit_price(self, provider: str, region: str, sku: str) -> float:
        """Region is accepted (the interface requires it) but not yet used --
        this table has no per-region pricing. `provider`/`region` are kept as
        parameters rather than dropped so a later region-aware table is a
        body change, not a signature change."""
        return _HOURLY_USD.get(sku, _DEFAULT_HOURLY_USD)

    async def is_available(self) -> bool:
        """A static table has nothing to be unreachable from."""
        return True

import json

import pytest

from kpi_sync.config import Config
from kpi_sync.envelope import KpiStore
from kpi_sync.pollers.onchain import (
    BurnVerificationPoller,
    OnchainBasePoller,
    OnchainEthPoller,
    PresaleActivity,
)


class FakeCall:
    def __init__(self, value):
        self._value = value

    async def call(self):
        return self._value


class FakeFunctions:
    def __init__(self, **values):
        self._values = values

    def __getattr__(self, name):
        value = self._values[name]
        return lambda *a, **kw: FakeCall(value)


class FakeContract:
    def __init__(self, **values):
        self.functions = FakeFunctions(**values)


# Values captured live from the Base presale contract (chain 8453) and the
# Ethereum CPX contract on 2026-07-20 via a public RPC, before this poller
# was written -- isPresaleActive genuinely reads True right now.
BASE_VALUES = dict(
    isPresaleActive=True,
    getTokenPrice=115130,
    presaleStart=1783012151,
    presaleEnd=1790788151,
    raisedFunds=0,
    contributorsAmount=0,
    ciphexSupply=64_000_000 * 10 ** 18,
)
ETH_TOTAL_SUPPLY = 1_500_000_000 * 10 ** 18


@pytest.mark.asyncio
async def test_onchain_base_poller_decodes_usd_and_cpx_and_flips_activity(fake_redis):
    store = KpiStore(fake_redis)
    activity = PresaleActivity()
    poller = OnchainBasePoller(store, activity)
    poller.contract = FakeContract(**BASE_VALUES)

    await poller.fetch_and_store()

    assert activity.active is True
    assert poller.get_interval_s() == Config.ONCHAIN_INTERVAL_S

    price = json.loads(await fake_redis.get("kpi:onchain_base:token_price"))
    assert price["value"]["raw"] == 115130
    assert price["value"]["usd"] == pytest.approx(0.11513)
    assert price["unit"] == "USD"

    remaining = json.loads(await fake_redis.get("kpi:onchain_base:remaining_cpx"))
    assert remaining["value"]["cpx"] == pytest.approx(64_000_000)

    active_flag = json.loads(await fake_redis.get("kpi:onchain_base:is_presale_active"))
    assert active_flag["value"] is True


@pytest.mark.asyncio
async def test_onchain_base_poller_backs_off_when_inactive(fake_redis):
    store = KpiStore(fake_redis)
    activity = PresaleActivity()
    poller = OnchainBasePoller(store, activity)
    inactive_values = dict(BASE_VALUES, isPresaleActive=False)
    poller.contract = FakeContract(**inactive_values)

    await poller.fetch_and_store()

    assert activity.active is False
    assert poller.get_interval_s() == Config.ONCHAIN_IDLE_INTERVAL_S


@pytest.mark.asyncio
async def test_onchain_eth_poller_reads_total_supply_and_shares_activity_interval(fake_redis):
    store = KpiStore(fake_redis)
    activity = PresaleActivity()
    activity.active = False  # simulate the Base poller having already gone idle
    poller = OnchainEthPoller(store, activity)
    poller.contract = FakeContract(totalSupply=ETH_TOTAL_SUPPLY)

    await poller.fetch_and_store()

    assert poller.get_interval_s() == Config.ONCHAIN_IDLE_INTERVAL_S
    total_supply = json.loads(await fake_redis.get("kpi:onchain_eth:total_supply"))
    assert total_supply["value"]["raw"] == ETH_TOTAL_SUPPLY
    assert total_supply["value"]["cpx"] == pytest.approx(1_500_000_000)
    assert total_supply["unit"] == "CPX"


# Auditor's reference values, 2026-07-20: verified live against the real
# Ethereum CPX contract + dead-address balance before this poller was
# written -- 1,500,000,000 - 481,454,298 = 1,018,545,702 exactly, matching
# the audit's stated FY2026 FD supply.
BURN_BALANCE_RAW = 481_454_298 * 10 ** 18


@pytest.mark.asyncio
async def test_burn_verification_poller_derives_effective_supply(fake_redis):
    store = KpiStore(fake_redis)
    poller = BurnVerificationPoller(store)
    poller.contract = FakeContract(totalSupply=ETH_TOTAL_SUPPLY, balanceOf=BURN_BALANCE_RAW)

    await poller.fetch_and_store()

    burn_balance = json.loads(await fake_redis.get("kpi:onchain:burn_balance_cpx"))
    assert burn_balance["value"]["raw"] == BURN_BALANCE_RAW
    assert burn_balance["value"]["cpx"] == pytest.approx(481_454_298)
    assert burn_balance["unit"] == "CPX"

    effective_supply = json.loads(await fake_redis.get("kpi:onchain:effective_supply_cpx"))
    assert effective_supply["value"]["raw"] == ETH_TOTAL_SUPPLY - BURN_BALANCE_RAW
    assert effective_supply["value"]["cpx"] == pytest.approx(1_018_545_702)


def test_burn_verification_poller_uses_its_own_hourly_cadence():
    poller = BurnVerificationPoller(KpiStore(None))
    assert poller.get_interval_s() == Config.BURN_VERIFICATION_INTERVAL_S
    assert poller.source_key == "onchain"

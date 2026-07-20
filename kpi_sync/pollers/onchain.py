"""On-chain reads: Base presale contract state + Ethereum CPX totalSupply.

ABI verified live against presale-live.js in the ciphex-website repo
(origin/main, commit 63fa729) and against the deployed contracts
themselves (Base chain 8453, Ethereum mainnet) before this was written.

Both cadences follow §4.1's "5 min while a round runs": PresaleActivity is
a small shared signal, set by OnchainBasePoller from the contract's own
isPresaleActive(), that OnchainEthPoller reads to pick its own interval --
the Ethereum totalSupply poller has no independent way to know whether a
round is running, and CONTRACTS.md ties its cadence to the same condition.
"""
from datetime import datetime, timezone
from typing import Optional

from web3 import AsyncWeb3

from kpi_sync.config import Config
from kpi_sync.envelope import KpiStore
from kpi_sync.pollers.base import BasePoller

PRESALE_ABI = [
    {"inputs": [], "name": "isPresaleActive", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "getTokenPrice", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "presaleStart", "outputs": [{"internalType": "uint32", "name": "", "type": "uint32"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "presaleEnd", "outputs": [{"internalType": "uint32", "name": "", "type": "uint32"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "raisedFunds", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "contributorsAmount", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "ciphexSupply", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
]

ERC20_TOTAL_SUPPLY_ABI = [
    {"constant": True, "inputs": [], "name": "totalSupply", "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
]

_USD_DECIMALS = 6  # matches presale-live.js formatUnits(priceRaw/raisedFundsRaw, 6)
_CPX_DECIMALS = 18


def _epoch_to_iso(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


class PresaleActivity:
    """Shared mutable signal read by OnchainEthPoller, written by
    OnchainBasePoller. Defaults to True so the very first cycle (before any
    Base read has completed) polls at the faster cadence rather than
    silently assuming the round is quiet."""

    def __init__(self) -> None:
        self.active = True


class OnchainBasePoller(BasePoller):
    source_key = "onchain_base"

    def __init__(self, store: KpiStore, activity: PresaleActivity):
        super().__init__(store)
        self.activity = activity
        self.w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(Config.BASE_RPC_URL))
        self.contract = self.w3.eth.contract(
            address=AsyncWeb3.to_checksum_address(Config.PRESALE_CONTRACT_ADDRESS),
            abi=PRESALE_ABI,
        )
        self.source_url = f"https://basescan.org/address/{Config.PRESALE_CONTRACT_ADDRESS}#readContract"

    def get_interval_s(self) -> int:
        return Config.ONCHAIN_INTERVAL_S if self.activity.active else Config.ONCHAIN_IDLE_INTERVAL_S

    async def fetch_and_store(self) -> None:
        fn = self.contract.functions
        active = await fn.isPresaleActive().call()
        price_raw = await fn.getTokenPrice().call()
        start = await fn.presaleStart().call()
        end = await fn.presaleEnd().call()
        raised_raw = await fn.raisedFunds().call()
        contributors = await fn.contributorsAmount().call()
        remaining_raw = await fn.ciphexSupply().call()

        self.activity.active = bool(active)

        writes = {
            "is_presale_active": (bool(active), None),
            "token_price": ({"raw": price_raw, "usd": price_raw / 10 ** _USD_DECIMALS}, "USD"),
            "raised_funds": ({"raw": raised_raw, "usd": raised_raw / 10 ** _USD_DECIMALS}, "USD"),
            "contributors_amount": (contributors, "count"),
            "remaining_cpx": (
                {"raw": remaining_raw, "cpx": remaining_raw / 10 ** _CPX_DECIMALS},
                "CPX",
            ),
            "presale_start": ({"epoch": start, "iso": _epoch_to_iso(start)}, None),
            "presale_end": ({"epoch": end, "iso": _epoch_to_iso(end)}, None),
        }
        for metric, (value, unit) in writes.items():
            await self.store.write_kpi(
                self.source_key,
                metric,
                value,
                unit=unit,
                source_url=self.source_url,
                as_of=None,  # on-chain reads are only as fresh as fetched_at; no separate upstream timestamp
                ttl_s=Config.DEFAULT_TTL_S,
                stale_after_s=Config.DEFAULT_STALE_AFTER_S,
            )


class OnchainEthPoller(BasePoller):
    source_key = "onchain_eth"

    def __init__(self, store: KpiStore, activity: PresaleActivity):
        super().__init__(store)
        self.activity = activity
        self.w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(Config.ETH_RPC_URL))
        self.contract = self.w3.eth.contract(
            address=AsyncWeb3.to_checksum_address(Config.CPX_ETH_CONTRACT_ADDRESS),
            abi=ERC20_TOTAL_SUPPLY_ABI,
        )
        self.source_url = f"https://etherscan.io/token/{Config.CPX_ETH_CONTRACT_ADDRESS}"

    def get_interval_s(self) -> int:
        return Config.ONCHAIN_INTERVAL_S if self.activity.active else Config.ONCHAIN_IDLE_INTERVAL_S

    async def fetch_and_store(self) -> None:
        total_supply_raw = await self.contract.functions.totalSupply().call()
        await self.store.write_kpi(
            self.source_key,
            "total_supply",
            {"raw": total_supply_raw, "cpx": total_supply_raw / 10 ** _CPX_DECIMALS},
            unit="CPX",
            source_url=self.source_url,
            as_of=None,
            ttl_s=Config.DEFAULT_TTL_S,
            stale_after_s=Config.DEFAULT_STALE_AFTER_S,
        )

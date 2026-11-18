"""Exercise bounded exploration without a database or network requests."""

from collections.abc import Iterable
from typing import Any, cast
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope import Scope
from app.models.Finding import Finding
from app.models.Target import Target
from app.services.adaptive import DEFAULT_MAX_DEPTH, AdaptiveResult, run_adaptive_scan
from app.services.scan import ScanResult


def finding(value: str, kind: str = "subdomain") -> Finding:
    return Finding(id=value, type=kind, value=value, normalized_value=value, source="test")


def scan_result(value: str, findings: Iterable[Finding] = ()) -> ScanResult:
    return ScanResult(target=Target(id=value, type="domain", value=value), findings=list(findings))


class AdaptiveScanTest(IsolatedAsyncioTestCase):
    async def run_with(self, scan: AsyncMock, **kwargs: Any) -> AdaptiveResult:
        with patch("app.services.adaptive.run_scan", new=scan):
            return await run_adaptive_scan(
                cast(AsyncSession, AsyncMock(spec=AsyncSession)),
                target_type="domain",
                target_value="example.com",
                **kwargs,
            )

    async def test_budget_includes_initial_target_and_records_skipped_leads(self) -> None:
        scan = AsyncMock(
            side_effect=lambda _, target_value, **kw: scan_result(
                target_value, [finding(f"host{i}.example.com") for i in range(8)]
            )
        )
        result = await self.run_with(scan, max_depth=4, max_targets=3)
        self.assertEqual(scan.await_count, 3)
        self.assertEqual(len(result.targets_scanned), 3)
        self.assertEqual(result.hop_count, 3)
        self.assertTrue(
            any("Target budget reached" in lead["reason"] for lead in result.leads_skipped)
        )

    async def test_default_stops_after_one_follow_up(self) -> None:
        scan = AsyncMock(
            side_effect=lambda _, target_value, **kw: scan_result(
                target_value, [finding("child." + target_value)]
            )
        )
        result = await self.run_with(scan)
        self.assertEqual(DEFAULT_MAX_DEPTH, 1)
        self.assertEqual([hop.depth for hop in result.hops], [0, 1])

    async def test_zero_depth_scans_initial_target_only(self) -> None:
        scan = AsyncMock(return_value=scan_result("example.com", [finding("a.example.com")]))
        result = await self.run_with(scan, max_depth=0)
        self.assertEqual(scan.await_count, 1)
        self.assertEqual(result.hops[0].leads_extracted, [])

    async def test_scoped_out_and_unsupported_targets_are_not_counted_as_scanned(self) -> None:
        scan = AsyncMock(
            return_value=scan_result(
                "example.com",
                [finding("outside.test"), finding("example.com A 192.0.2.1", "dns_record")],
            )
        )
        result = await self.run_with(scan, scope=Scope(allowed_domains=["example.com"]))
        self.assertEqual(result.targets_scanned, {("domain", "example.com")})
        self.assertEqual(len(result.leads_skipped), 2)
        self.assertEqual(scan.await_count, 1)

    async def test_nameserver_infrastructure_is_left_for_manual_review(self) -> None:
        scan = AsyncMock(
            side_effect=lambda _, target_value, **kw: scan_result(
                target_value, [finding("a.example.com"), finding("ns.shared.test", "nameserver")]
            )
        )
        result = await self.run_with(scan)
        self.assertEqual(
            result.targets_scanned, {("domain", "example.com"), ("domain", "a.example.com")}
        )
        self.assertTrue(any("manual review" in lead["reason"] for lead in result.leads_skipped))

    async def test_cycles_do_not_scan_a_target_twice(self) -> None:
        scan = AsyncMock(return_value=scan_result("example.com", [finding("example.com")]))
        result = await self.run_with(scan, max_depth=4)
        self.assertEqual(scan.await_count, 1)
        self.assertEqual(len(result.leads_skipped), 1)

    async def test_invalid_limits_fail_before_any_scan(self) -> None:
        scan = AsyncMock()
        for kwargs in [
            {"max_targets": 0},
            {"max_targets": 101},
            {"max_depth": -1},
            {"max_depth": 5},
        ]:
            with self.subTest(**kwargs), self.assertRaises(ValueError):
                await self.run_with(scan, **kwargs)
        scan.assert_not_awaited()

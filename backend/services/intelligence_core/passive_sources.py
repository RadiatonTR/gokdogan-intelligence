from __future__ import annotations

import asyncio
import html
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx

from .source_health import SourceHealthRegistry, SourcePolicy

_USER_AGENT = "ShadowBroker-Intelligence-Desktop/0.9.88-R9"


def _strip_html(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(value))).strip()


class PassiveSourceHub:
    """Passive/public intelligence adapters.

    These adapters do not scan hosts or enumerate private systems. All network
    requests target documented public-data endpoints and are routed through the
    Intelligence Core circuit-breaker/source-health registry.
    """

    def __init__(self, registry: SourceHealthRegistry) -> None:
        self.registry = registry
        self.timeout = httpx.Timeout(20.0, connect=8.0)
        self._register_sources()

    def _register_sources(self) -> None:
        for source_id, provider, reliability, stale_after in [
            ("cisa_kev", "CISA KEV", 0.99, 86_400),
            ("who_don", "WHO Disease Outbreak News", 0.97, 21_600),
            ("reliefweb", "ReliefWeb / UN OCHA", 0.96, 7_200),
            ("hdx", "Humanitarian Data Exchange", 0.93, 21_600),
            ("safecast", "Safecast", 0.78, 7_200),
            ("epa_radnet", "EPA RadNet", 0.97, 21_600),
            ("un_comtrade", "UN Comtrade", 0.96, 86_400),
            ("fred", "FRED", 0.98, 86_400),
            ("bls", "US Bureau of Labor Statistics", 0.98, 86_400),
            ("eia", "US Energy Information Administration", 0.98, 86_400),
            ("us_treasury", "US Treasury Fiscal Data", 0.99, 86_400),
            ("usaspending", "USAspending", 0.97, 86_400),
            ("gscpi", "NY Fed GSCPI", 0.98, 2_592_000),
        ]:
            self.registry.register(
                source_id,
                provider,
                SourcePolicy(
                    max_failures=2,
                    cooldown_seconds=300,
                    stale_after_seconds=stale_after,
                    reliability=reliability,
                ),
                {"owner": "intelligence-core", "mode": "passive-public-data"},
            )

    async def _json(
        self, source_id: str, provider: str, method: str, url: str, **kwargs: Any
    ) -> Any:
        async def do_request() -> Any:
            headers = {
                "User-Agent": _USER_AGENT,
                "Accept": "application/json",
                **kwargs.pop("headers", {}),
            }
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True, headers=headers
            ) as client:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                return response.json()

        return await self.registry.call(source_id, provider, do_request)

    async def cisa_kev(self, limit: int = 30) -> dict[str, Any]:
        url = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
        data = await self._json("cisa_kev", "CISA KEV", "GET", url)
        vulnerabilities = list(data.get("vulnerabilities") or [])
        vulnerabilities.sort(
            key=lambda item: str(item.get("dateAdded") or ""), reverse=True
        )
        cutoff = datetime.now(UTC).date() - timedelta(days=30)
        recent_count = 0
        ransomware = 0
        overdue = 0
        now = datetime.now(UTC).date()
        for item in vulnerabilities:
            try:
                if datetime.fromisoformat(str(item.get("dateAdded"))).date() >= cutoff:
                    recent_count += 1
            except Exception:
                pass
            if str(item.get("knownRansomwareCampaignUse") or "").lower() == "known":
                ransomware += 1
            try:
                if datetime.fromisoformat(str(item.get("dueDate"))).date() < now:
                    overdue += 1
            except Exception:
                pass
        recent = [
            {
                "cve": v.get("cveID"),
                "vendor": v.get("vendorProject"),
                "product": v.get("product"),
                "name": v.get("vulnerabilityName"),
                "date_added": v.get("dateAdded"),
                "due_date": v.get("dueDate"),
                "ransomware": v.get("knownRansomwareCampaignUse"),
                "description": str(v.get("shortDescription") or "")[:500],
            }
            for v in vulnerabilities[: max(1, min(limit, 100))]
        ]
        return {
            "source": "CISA KEV",
            "catalog_version": data.get("catalogVersion"),
            "date_released": data.get("dateReleased"),
            "summary": {
                "total": len(vulnerabilities),
                "added_last_30d": recent_count,
                "ransomware_linked": ransomware,
                "overdue": overdue,
            },
            "items": recent,
        }

    async def who_outbreaks(self, limit: int = 25) -> dict[str, Any]:
        data = await self._json(
            "who_don",
            "WHO Disease Outbreak News",
            "GET",
            "https://www.who.int/api/news/diseaseoutbreaknews",
        )
        items = list(data.get("value") or [])
        items.sort(key=lambda x: str(x.get("PublicationDate") or ""), reverse=True)
        cutoff = datetime.now(UTC) - timedelta(days=60)
        out: list[dict[str, Any]] = []
        for item in items:
            stamp = item.get("PublicationDate")
            try:
                when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=UTC)
                if when < cutoff:
                    continue
            except Exception:
                pass
            relative = str(item.get("ItemDefaultUrl") or "")
            out.append(
                {
                    "title": item.get("Title"),
                    "date": stamp,
                    "don_id": item.get("DonId"),
                    "url": f"https://www.who.int/emergencies/disease-outbreak-news{relative}"
                    if relative.startswith("/")
                    else relative or None,
                    "summary": _strip_html(item.get("Summary") or item.get("Overview"))[
                        :600
                    ],
                }
            )
            if len(out) >= max(1, min(limit, 100)):
                break
        return {"source": "WHO", "items": out, "count": len(out)}

    async def reliefweb(self, query: str = "", limit: int = 20) -> dict[str, Any]:
        limit = max(1, min(limit, 50))
        appname = os.getenv("RELIEFWEB_APPNAME", "").strip()
        if appname:
            body: dict[str, Any] = {
                "limit": limit,
                "fields": {
                    "include": [
                        "title",
                        "date.created",
                        "country.name",
                        "disaster_type.name",
                        "url_alias",
                        "source.name",
                    ]
                },
                "sort": ["date.created:desc"],
            }
            if query.strip():
                body["query"] = {"value": query.strip()[:300]}
            try:
                data = await self._json(
                    "reliefweb",
                    "ReliefWeb / UN OCHA",
                    "POST",
                    f"https://api.reliefweb.int/v1/reports?appname={quote(appname)}",
                    json=body,
                    headers={"Content-Type": "application/json"},
                )
                items = []
                for row in list(data.get("data") or []):
                    fields = row.get("fields") or {}
                    alias = fields.get("url_alias")
                    items.append(
                        {
                            "title": fields.get("title"),
                            "date": (fields.get("date") or {}).get("created"),
                            "countries": [
                                x.get("name")
                                for x in fields.get("country") or []
                                if x.get("name")
                            ],
                            "disaster_types": [
                                x.get("name")
                                for x in fields.get("disaster_type") or []
                                if x.get("name")
                            ],
                            "sources": [
                                x.get("name")
                                for x in fields.get("source") or []
                                if x.get("name")
                            ],
                            "url": f"https://reliefweb.int{alias}" if alias else None,
                        }
                    )
                return {"source": "ReliefWeb", "mode": "reliefweb", "items": items}
            except Exception:
                # Continue with HDX fallback; the failure is retained by source-health.
                pass

        search = query.strip() or "crisis disaster emergency"
        url = f"https://data.humdata.org/api/3/action/package_search?q={quote(search)}&rows={limit}&sort=metadata_modified%20desc"
        data = await self._json("hdx", "Humanitarian Data Exchange", "GET", url)
        rows = ((data or {}).get("result") or {}).get("results") or []
        items = [
            {
                "title": row.get("title"),
                "date": row.get("metadata_modified"),
                "organization": (row.get("organization") or {}).get("title"),
                "countries": [
                    g.get("display_name")
                    for g in row.get("groups") or []
                    if g.get("display_name")
                ],
                "url": f"https://data.humdata.org/dataset/{row.get('name')}"
                if row.get("name")
                else None,
            }
            for row in rows[:limit]
        ]
        return {
            "source": "HDX",
            "mode": "hdx-fallback",
            "items": items,
            "reliefweb_appname_configured": bool(appname),
        }

    async def safecast(
        self,
        latitude: float | None = None,
        longitude: float | None = None,
        distance_km: float = 100,
        limit: int = 50,
    ) -> dict[str, Any]:
        limit = max(1, min(limit, 200))
        params = [f"limit={limit}"]
        if latitude is not None and longitude is not None:
            params += [
                f"latitude={latitude:.6f}",
                f"longitude={longitude:.6f}",
                f"distance={max(1.0, min(distance_km, 1000.0)) * 1000:.0f}",
            ]
        data = await self._json(
            "safecast",
            "Safecast",
            "GET",
            "https://api.safecast.org/measurements.json?" + "&".join(params),
        )
        rows = data if isinstance(data, list) else []
        values = [
            float(x.get("value"))
            for x in rows
            if isinstance(x, dict) and isinstance(x.get("value"), (int, float))
        ]
        return {
            "source": "Safecast",
            "count": len(rows),
            "summary": {
                "average": sum(values) / len(values) if values else None,
                "maximum": max(values) if values else None,
            },
            "items": rows[:limit],
        }

    async def epa_radnet(self, rows: int = 100) -> dict[str, Any]:
        rows = max(1, min(rows, 250))
        url = f"https://enviro.epa.gov/enviro/efservice/RADNET_ANALYTICAL_RESULTS/ROWS/0:{rows}/JSON"
        data = await self._json("epa_radnet", "EPA RadNet", "GET", url)
        items = data if isinstance(data, list) else []
        compact = []
        for row in items[:rows]:
            compact.append(
                {
                    "location": row.get("ANA_CITY") or row.get("LOCATION"),
                    "state": row.get("ANA_STATE") or row.get("STATE"),
                    "analyte": row.get("ANA_TYPE") or row.get("ANALYTE_NAME"),
                    "result": row.get("ANA_RESULT"),
                    "unit": row.get("RESULT_UNIT") or row.get("ANA_UNIT"),
                    "date": row.get("COLLECT_DATE") or row.get("SAMPLE_DATE"),
                    "medium": row.get("SAMPLE_TYPE") or row.get("MEDIUM"),
                }
            )
        return {"source": "EPA RadNet", "count": len(compact), "items": compact}

    async def comtrade(
        self,
        reporter_code: int = 842,
        commodity: str = "2709",
        period: int | None = None,
        flow_code: str = "M",
        limit: int = 50,
    ) -> dict[str, Any]:
        period = period or datetime.now(UTC).year
        commodity = re.sub(r"[^0-9]", "", commodity)[:6] or "2709"
        flow_code = "X" if flow_code.upper() == "X" else "M"
        url = (
            "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
            f"?reporterCode={int(reporter_code)}&period={int(period)}&cmdCode={commodity}&flowCode={flow_code}"
        )
        data = await self._json("un_comtrade", "UN Comtrade", "GET", url)
        rows = (data or {}).get("data") or (data or {}).get("dataset") or []
        if not isinstance(rows, list):
            rows = []
        out = []
        for row in rows[: max(1, min(limit, 100))]:
            out.append(
                {
                    "reporter": row.get("reporterDesc") or row.get("reporterCode"),
                    "partner": row.get("partnerDesc") or row.get("partnerCode"),
                    "commodity": row.get("cmdDesc") or row.get("cmdCode"),
                    "flow": row.get("flowDesc") or row.get("flowCode"),
                    "value": row.get("primaryValue")
                    or row.get("cifvalue")
                    or row.get("fobvalue"),
                    "quantity": row.get("qty") or row.get("netWgt"),
                    "period": row.get("period"),
                }
            )
        return {
            "source": "UN Comtrade",
            "reporter_code": reporter_code,
            "commodity": commodity,
            "period": period,
            "flow": flow_code,
            "items": out,
        }

    async def fred(self, series_id: str, limit: int = 60) -> dict[str, Any]:
        key = os.getenv("FRED_API_KEY", "").strip()
        if not key:
            self.registry.record_failure("fred", "FRED", "FRED_API_KEY missing")
            return {
                "source": "FRED",
                "configured": False,
                "items": [],
                "error": "FRED_API_KEY is not configured",
            }
        series_id = re.sub(r"[^A-Za-z0-9_.-]", "", series_id)[:64]
        url = (
            "https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={quote(series_id)}&api_key={quote(key)}&file_type=json&sort_order=desc&limit={max(1, min(limit, 500))}"
        )
        data = await self._json("fred", "FRED", "GET", url)
        return {
            "source": "FRED",
            "configured": True,
            "series_id": series_id,
            "items": list(data.get("observations") or []),
        }

    async def bls(self, series_ids: list[str] | None = None) -> dict[str, Any]:
        ids = series_ids or [
            "CUUR0000SA0",
            "CUUR0000SA0L1E",
            "LNS14000000",
            "CES0000000001",
            "WPUFD49104",
        ]
        ids = [re.sub(r"[^A-Za-z0-9]", "", x)[:32] for x in ids[:20] if x]
        year = datetime.now(UTC).year
        payload: dict[str, Any] = {
            "seriesid": ids,
            "startyear": str(year - 1),
            "endyear": str(year),
        }
        api_key = os.getenv("BLS_API_KEY", "").strip()
        if api_key:
            payload["registrationkey"] = api_key
        data = await self._json(
            "bls",
            "US Bureau of Labor Statistics",
            "POST",
            "https://api.bls.gov/publicAPI/v2/timeseries/data/"
            if api_key
            else "https://api.bls.gov/publicAPI/v1/timeseries/data/",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        series = ((data or {}).get("Results") or {}).get("series") or []
        return {
            "source": "BLS",
            "configured_key": bool(api_key),
            "status": data.get("status"),
            "series": series,
        }

    async def eia(self, length: int = 10) -> dict[str, Any]:
        key = os.getenv("EIA_API_KEY", "").strip()
        if not key:
            self.registry.record_failure(
                "eia", "US Energy Information Administration", "EIA_API_KEY missing"
            )
            return {
                "source": "EIA",
                "configured": False,
                "series": {},
                "error": "EIA_API_KEY is not configured",
            }
        length = max(1, min(length, 100))
        defs = {
            "wti": ("petroleum/pri/spt/data/", "daily", "RWTC"),
            "brent": ("petroleum/pri/spt/data/", "daily", "RBRTE"),
            "henry_hub": ("natural-gas/pri/fut/data/", "daily", "RNGWHHD"),
            "crude_stocks": ("petroleum/stoc/wstk/data/", "weekly", "WCESTUS1"),
        }

        async def one(name: str, spec: tuple[str, str, str]) -> tuple[str, Any]:
            path, frequency, series = spec
            url = (
                f"https://api.eia.gov/v2/{path}?api_key={quote(key)}&frequency={frequency}&data[0]=value"
                f"&facets[series][]={series}&sort[0][column]=period&sort[0][direction]=desc&length={length}"
            )
            try:
                data = await self._json(
                    "eia", "US Energy Information Administration", "GET", url
                )
                return name, (((data or {}).get("response") or {}).get("data") or [])
            except Exception as exc:
                return name, {"error": type(exc).__name__}

        pairs = await asyncio.gather(*(one(name, spec) for name, spec in defs.items()))
        return {"source": "EIA", "configured": True, "series": dict(pairs)}

    async def treasury(self, days: int = 14) -> dict[str, Any]:
        days = max(1, min(days, 365))
        start = (datetime.now(UTC).date() - timedelta(days=days)).isoformat()
        base = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
        debt_url = (
            f"{base}/v2/accounting/od/debt_to_penny?fields=record_date,tot_pub_debt_out_amt,intragov_hold_amt,debt_held_public_amt"
            f"&sort=-record_date&page[size]=30&filter=record_date:gte:{start}"
        )
        rates_url = (
            f"{base}/v2/accounting/od/avg_interest_rates?fields=record_date,security_desc,avg_interest_rate_amt"
            f"&sort=-record_date&page[size]=50&filter=record_date:gte:{start}"
        )
        debt, rates = await asyncio.gather(
            self._json("us_treasury", "US Treasury Fiscal Data", "GET", debt_url),
            self._json("us_treasury", "US Treasury Fiscal Data", "GET", rates_url),
        )
        return {
            "source": "US Treasury",
            "debt": list((debt or {}).get("data") or [])[:10],
            "interest_rates": list((rates or {}).get("data") or [])[:50],
        }

    async def usaspending(self, days: int = 30, limit: int = 20) -> dict[str, Any]:
        days = max(1, min(days, 365))
        limit = max(1, min(limit, 100))
        start = (datetime.now(UTC).date() - timedelta(days=days)).isoformat()
        end = datetime.now(UTC).date().isoformat()
        body = {
            "filters": {
                "keywords": ["defense", "military", "missile", "aircraft", "naval"],
                "time_period": [{"start_date": start, "end_date": end}],
                "award_type_codes": ["A", "B", "C", "D"],
            },
            "fields": [
                "Award ID",
                "Recipient Name",
                "Award Amount",
                "Description",
                "Awarding Agency",
                "Start Date",
                "Award Type",
            ],
            "limit": limit,
            "page": 1,
            "sort": "Award Amount",
            "order": "desc",
        }
        data = await self._json(
            "usaspending",
            "USAspending",
            "POST",
            "https://api.usaspending.gov/api/v2/search/spending_by_award/",
            json=body,
            headers={"Content-Type": "application/json"},
        )
        return {
            "source": "USAspending",
            "days": days,
            "items": list((data or {}).get("results") or [])[:limit],
        }

    async def gscpi(self, months: int = 24) -> dict[str, Any]:
        months = max(1, min(months, 240))

        async def get_text() -> str:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": _USER_AGENT},
            ) as client:
                response = await client.get(
                    "https://www.newyorkfed.org/medialibrary/research/interactives/data/gscpi/gscpi_interactive_data.csv"
                )
                response.raise_for_status()
                return response.text

        text = await self.registry.call("gscpi", "NY Fed GSCPI", get_text)
        month_map = {
            "Jan": "01",
            "Feb": "02",
            "Mar": "03",
            "Apr": "04",
            "May": "05",
            "Jun": "06",
            "Jul": "07",
            "Aug": "08",
            "Sep": "09",
            "Oct": "10",
            "Nov": "11",
            "Dec": "12",
        }
        items = []
        for line in text.splitlines()[1:]:
            cols = [x.strip() for x in line.split(",")]
            if not cols or not cols[0]:
                continue
            parts = cols[0].split("-")
            if len(parts) != 3 or parts[1] not in month_map:
                continue
            value = None
            for raw in reversed(cols[1:]):
                try:
                    if raw and raw != "#N/A":
                        value = float(raw)
                        break
                except ValueError:
                    pass
            if value is not None:
                items.append(
                    {"date": f"{parts[2]}-{month_map[parts[1]]}", "value": value}
                )
        items.sort(key=lambda x: x["date"], reverse=True)
        history = items[:months]
        trend = "stable"
        if len(history) >= 3:
            recent = [x["value"] for x in history[:3]]
            trend = (
                "rising"
                if recent[0] > recent[1] > recent[2]
                else "falling"
                if recent[0] < recent[1] < recent[2]
                else "stable"
            )
        return {
            "source": "NY Fed GSCPI",
            "latest": history[0] if history else None,
            "trend": trend,
            "history": history,
        }

    async def dashboard(self) -> dict[str, Any]:
        """Fetch a small passive cross-domain briefing without failing wholesale."""

        async def capture(name: str, coro: Any) -> tuple[str, Any]:
            try:
                return name, await coro
            except Exception as exc:
                return name, {"error": type(exc).__name__, "detail": str(exc)[:300]}

        pairs = await asyncio.gather(
            capture("cisa_kev", self.cisa_kev(15)),
            capture("who", self.who_outbreaks(10)),
            capture("humanitarian", self.reliefweb(limit=10)),
        )
        return {"generated_at": datetime.now(UTC).isoformat(), "sources": dict(pairs)}

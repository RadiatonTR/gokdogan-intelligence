"""USNI News Fleet & Marine Tracker — authoritative weekly carrier
position publication.

Why this exists
---------------
The previous carrier_tracker pipeline relied on GDELT headline matching
(``api.gdeltproject.org``) to derive positions from text like "USS Ford
in the Mediterranean" → centroid of "Mediterranean Sea". That was
- low-precision (audit issue #245 — false precision from text mentions),
- unreliable (``api.gdeltproject.org`` is sometimes unreachable from
  certain network paths, including Docker Desktop on some Windows hosts).

USNI publishes a weekly tracker that explicitly lists where every U.S.
carrier is operating. The article body uses extremely consistent phrasing:

    "The Gerald R. Ford Carrier Strike Group is operating in the Red Sea"
    "Aircraft carrier USS George Washington (CVN-73) is in port in
     Yokosuka, Japan."
    "USS Dwight D. Eisenhower (CVN-69) sails down the Elizabeth River"

Those are deterministic to parse. This module:

  1. Pulls the WordPress RSS feeds (both site-wide and category) — the
     site-wide feed often has fresher posts before the category feed
     catches up, so we union them.
  2. Picks the most recent post by parsed ``pubDate``.
  3. For each carrier in the registry, scans the article body for a
     "is operating in / is in port in / departed from" pattern near
     the carrier's name.
  4. Maps the extracted region phrase to coordinates via the carrier
     tracker's existing REGION_COORDS.

The result is a ``{hull: position_entry}`` dict that the carrier tracker
consumes as a high-confidence source — ``position_confidence: "recent"``
with ``position_source_at`` set to the article's actual publication
timestamp (not ``now()``).

Politeness
----------
We send the per-install operator handle via ``outbound_user_agent``
(Round 7a) so USNI can rate-limit / contact the specific install if
needed. Article-body pages return 403 to non-browser UAs (Cloudflare),
but WordPress RSS feeds are open and serve the full article in
``<content:encoded>`` — that's the supported path for aggregators and
the one we use. We do not spoof browser headers.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable

from services.network_utils import fetch_with_curl, outbound_user_agent

logger = logging.getLogger(__name__)

_RSS_URLS: tuple[str, ...] = (
    # Site-wide feed often has the freshest posts before the category
    # feed catches up. We try this first.
    "https://news.usni.org/feed",
    # Category feed has older fleet trackers for backfill.
    "https://news.usni.org/category/fleet-tracker/feed",
)

_RSS_NS = {"content": "http://purl.org/rss/1.0/modules/content/"}

_FLEET_TRACKER_TITLE_RE = re.compile(
    r"fleet\s+and\s+marine\s+tracker", re.IGNORECASE
)

_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_html(html: str) -> str:
    text = _TAG_STRIP_RE.sub(" ", html or "")
    return _WHITESPACE_RE.sub(" ", text).strip()


def _request_headers() -> dict[str, str]:
    """Headers USNI's WordPress feed accepts from a legitimate aggregator.

    The ``Referer`` is the category index page — that's where a real
    feed reader navigates from. ``Accept`` declares RSS preference but
    falls back to HTML. No browser UA spoofing.
    """
    return {
        "User-Agent": outbound_user_agent("usni-fleet-tracker"),
        "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.1",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://news.usni.org/category/fleet-tracker",
    }


def _parse_pubdate(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def _iter_fleet_tracker_items(rss_urls: Iterable[str]) -> list[dict]:
    """Pull every fleet-tracker post visible across the given RSS feeds.

    De-duplicates by article link. Returns a list of dicts:
        {"title", "link", "pub_date" (datetime), "body" (plain text)}
    """
    items_by_link: dict[str, dict] = {}
    for url in rss_urls:
        try:
            r = fetch_with_curl(url, timeout=15, headers=_request_headers())
        except Exception as exc:
            logger.debug("USNI RSS %s exception: %s", url, exc)
            continue
        if not r or r.status_code != 200 or not r.text:
            logger.debug(
                "USNI RSS %s returned status=%s body=%d",
                url,
                getattr(r, "status_code", "?"),
                len(getattr(r, "text", "") or ""),
            )
            continue
        try:
            root = ET.fromstring(r.text)
        except ET.ParseError as exc:
            logger.warning("USNI RSS parse error from %s: %s", url, exc)
            continue
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            if not _FLEET_TRACKER_TITLE_RE.search(title):
                continue
            link = (item.findtext("link") or "").strip()
            if not link or link in items_by_link:
                continue
            pub_dt = _parse_pubdate(item.findtext("pubDate") or "")
            body_html = (
                item.findtext("content:encoded", default="", namespaces=_RSS_NS)
                or item.findtext("description", default="")
                or ""
            )
            items_by_link[link] = {
                "title": title,
                "link": link,
                "pub_date": pub_dt,
                "body": _strip_html(body_html),
            }
    return list(items_by_link.values())


# Map USNI region phrases to keys in carrier_tracker.REGION_COORDS.
# The carrier_tracker table already covers most named bodies of water and
# major ports — we just need to teach this module to RECOGNIZE the
# specific phrases USNI's editorial style uses, which sometimes spell
# the same body of water differently.
_USNI_REGION_ALIASES: tuple[tuple[str, str], ...] = (
    # USNI phrase (lowercase) -> REGION_COORDS key
    ("eastern mediterranean", "eastern mediterranean"),
    ("western mediterranean", "western mediterranean"),
    ("mediterranean sea", "mediterranean"),
    ("the mediterranean", "mediterranean"),
    ("red sea", "red sea"),
    ("arabian sea area of responsibility", "arabian sea"),
    ("north arabian sea", "north arabian sea"),
    ("arabian sea", "arabian sea"),
    ("persian gulf", "persian gulf"),
    ("gulf of oman", "gulf of oman"),
    ("strait of hormuz", "strait of hormuz"),
    ("south china sea", "south china sea"),
    ("east china sea", "east china sea"),
    ("philippine sea", "philippine sea"),
    ("sea of japan", "sea of japan"),
    ("taiwan strait", "taiwan strait"),
    ("western pacific", "western pacific"),
    ("pacific ocean", "pacific"),
    ("indian ocean", "indian ocean"),
    ("north atlantic", "north atlantic"),
    ("western atlantic", "atlantic"),
    ("eastern atlantic", "atlantic"),
    ("atlantic ocean", "atlantic"),
    ("gulf of aden", "gulf of aden"),
    ("horn of africa", "horn of africa"),
    ("bab el-mandeb", "bab el-mandeb"),
    ("suez canal", "suez canal"),
    ("baltic sea", "baltic sea"),
    ("north sea", "north sea"),
    ("black sea", "black sea"),
    ("south atlantic", "south atlantic"),
    ("coral sea", "coral sea"),
    ("gulf of mexico", "gulf of mexico"),
    ("caribbean sea", "caribbean"),
    ("caribbean", "caribbean"),
    # Specific ports
    ("naval station norfolk", "norfolk"),
    ("norfolk naval shipyard", "newport news"),
    ("newport news shipbuilding", "newport news"),
    ("newport news", "newport news"),
    # USNI tags Norfolk mentions with state suffix; match both.
    ("norfolk, va", "norfolk"),
    ("norfolk", "norfolk"),
    ("naval station everett", "puget sound"),
    ("naval base kitsap", "bremerton"),
    ("bremerton", "bremerton"),
    ("puget sound", "puget sound"),
    ("naval base san diego", "san diego"),
    ("san diego, calif", "san diego"),
    ("san diego", "san diego"),
    ("yokosuka, japan", "yokosuka"),
    ("yokosuka", "yokosuka"),
    ("pearl harbor", "pearl harbor"),
    ("apra harbor, guam", "guam"),
    ("guam", "guam"),
    ("bahrain", "bahrain"),
    ("naval station rota", "rota"),
    ("rota, spain", "rota"),
    ("naples, italy", "naples"),
    # Fleets / AORs
    ("5th fleet", "5th fleet"),
    ("6th fleet", "6th fleet"),
    ("7th fleet", "7th fleet"),
    ("3rd fleet", "3rd fleet"),
    ("2nd fleet", "2nd fleet"),
    ("centcom", "centcom"),
    ("indo-pacific command", "indopacom"),
    ("eucom", "eucom"),
    ("southcom", "southcom"),
)


def _resolve_region_phrase(phrase: str) -> tuple[str, str] | None:
    """Map a USNI region phrase to a ``(canonical_key, display)`` tuple,
    or ``None`` if we don't recognize it.

    ``canonical_key`` is what ``carrier_tracker.REGION_COORDS`` keys on.
    ``display`` is the phrase we'll show in the dossier description.
    """
    p = (phrase or "").lower().strip()
    if not p:
        return None
    for usni_phrase, canonical in _USNI_REGION_ALIASES:
        if usni_phrase in p:
            return canonical, usni_phrase
    return None


# Operating-verb phrases USNI uses, with a capture group for the region
# phrase that immediately follows. Each pattern is designed to swallow
# the optional editorial filler that often appears between verb and
# location (e.g. "returned Friday to Norfolk" — "Friday" goes in the
# filler; "Norfolk" is the location).
#
# Order matters: most-specific patterns first, so e.g. "is in port in"
# wins over the generic "is".
_DAY_FILLER = r"(?:[A-Z][a-z]+(?:day)?,?\s+)?"  # optional "Friday" / "Monday" / etc.
_LOC_CAPTURE = r"([A-Za-z][A-Za-z0-9\s,\.\-']{2,80})"

_OPERATING_PATTERNS: tuple[re.Pattern, ...] = (
    # "is operating in [the] {REGION}" / "is also operating in [the] {REGION}"
    re.compile(r"\bis\s+(?:also\s+|now\s+)?operating\s+in\s+(?:the\s+)?" + _LOC_CAPTURE, re.IGNORECASE),
    # "is conducting <stuff> in [the] {REGION}"
    re.compile(r"\bis\s+conducting\s+[A-Za-z0-9\-\s]{2,40}\s+in\s+(?:the\s+)?" + _LOC_CAPTURE, re.IGNORECASE),
    # "is in port in {LOCATION}"
    re.compile(r"\bis\s+in\s+port\s+in\s+" + _LOC_CAPTURE, re.IGNORECASE),
    # "is in port" (no location — degenerate, use carrier's homeport via separate path)
    # → not captured here; falls through to homeport
    # "is underway in [the] {REGION}"
    re.compile(r"\bis\s+underway\s+in\s+(?:the\s+)?" + _LOC_CAPTURE, re.IGNORECASE),
    # "is deployed to [the] {REGION}" / "deployed in"
    re.compile(r"\bis\s+deployed\s+(?:to|in)\s+(?:the\s+)?" + _LOC_CAPTURE, re.IGNORECASE),
    # "returned [Day] to {LOCATION}" / "returned [Day] from {REGION}"
    re.compile(r"\breturned\s+" + _DAY_FILLER + r"to\s+" + _LOC_CAPTURE, re.IGNORECASE),
    re.compile(r"\breturned\s+" + _DAY_FILLER + r"from\s+(?:the\s+)?" + _LOC_CAPTURE, re.IGNORECASE),
    # "arrived [Day] in/at {LOCATION}"
    re.compile(r"\barrived\s+" + _DAY_FILLER + r"(?:in|at)\s+" + _LOC_CAPTURE, re.IGNORECASE),
    # "departed [Day] from {LOCATION}"
    re.compile(r"\bdeparted\s+" + _DAY_FILLER + r"(?:from\s+)?" + _LOC_CAPTURE, re.IGNORECASE),
    # "transiting [the] {REGION}" / "sailing through [the] {REGION}"
    re.compile(r"\btransiting\s+(?:the\s+)?" + _LOC_CAPTURE, re.IGNORECASE),
    re.compile(r"\bsailing\s+through\s+(?:the\s+)?" + _LOC_CAPTURE, re.IGNORECASE),
    # "is homeported at {LOCATION}"
    re.compile(r"\bis\s+homeported\s+at\s+" + _LOC_CAPTURE, re.IGNORECASE),
)


def _extract_region_for_carrier(
    body: str,
    carrier_names: list[str],
    hull_code: str,
) -> str | None:
    """Return the best-guess region phrase for one carrier from the
    article body, or None if no confident match.

    Algorithm:
      1. Find every mention of the carrier (any name variant or the hull
         code) in the body.
      2. For each mention, look in the ~300-char window AFTER it for any
         of the operating-verb patterns.
      3. Return the first hit. If a more-confident match later turns up
         (e.g. "is operating in the X" beats "is homeported at Y"), the
         first one in document order still wins — USNI's structure puts
         the position-update sentence near the top of each carrier's
         section, and the homeport mention later.
    """
    # Build a master mention regex covering every name variant + the hull.
    candidates: list[str] = []
    for name in carrier_names:
        if name and len(name) >= 4:
            candidates.append(re.escape(name))
    if hull_code:
        candidates.append(re.escape(hull_code))
    if not candidates:
        return None
    mention_re = re.compile(r"\b(?:" + "|".join(candidates) + r")\b", re.IGNORECASE)

    window_chars = 320
    seen_phrases: list[str] = []
    for mention in mention_re.finditer(body):
        end = mention.end()
        window = body[end : end + window_chars]
        # Cut window at the next sentence break for tighter context.
        # (We use the LAST period within the window so "Norfolk, Va." isn't
        # confused for a sentence end — USNI uses ", Va." prolifically.)
        # Sentence break candidates: ". " followed by uppercase OR newline.
        sent_break = re.search(r"[\.!?]\s+[A-Z]", window)
        if sent_break:
            window = window[: sent_break.start() + 1]
        # Try patterns in priority order.
        for pat in _OPERATING_PATTERNS:
            m = pat.search(window)
            if not m:
                continue
            phrase = m.group(1).strip().rstrip(",.;: ")
            if not phrase:
                continue
            # Strip trailing editorial filler — USNI often writes
            # "Norfolk, Va., according to ship spotters" or
            # "Yokosuka, Japan, according to..."
            phrase = re.split(
                r",\s+(?:according|as of|for|while|where|in support|in the)",
                phrase,
                maxsplit=1,
            )[0].strip()
            seen_phrases.append(phrase)
            return phrase
    return seen_phrases[0] if seen_phrases else None


def fetch_latest_fleet_tracker_positions(
    carrier_registry: dict | None = None,
    region_coords: dict | None = None,
) -> dict[str, dict]:
    """Return ``{hull: position_entry}`` for the latest USNI fleet tracker.

    Entries look like::

        {
          "lat": 18.0, "lng": 39.5, "heading": 0,
          "desc": "Red Sea (USNI May 18, 2026)",
          "source": "USNI News Fleet & Marine Tracker (May 18, 2026)",
          "source_url": "https://news.usni.org/2026/05/18/...",
          "position_source_at": "2026-05-18T18:58:44+00:00",
          "position_confidence": "recent",
        }

    Carriers whose section can't be parsed (e.g. an off-week with no
    mention) are simply absent from the result — the caller keeps
    whatever position they had before.

    ``carrier_registry`` and ``region_coords`` default to the carrier_tracker
    module's own tables; passed in here for testability.
    """
    if carrier_registry is None or region_coords is None:
        from services.carrier_tracker import CARRIER_REGISTRY, REGION_COORDS
        carrier_registry = carrier_registry or CARRIER_REGISTRY
        region_coords = region_coords or REGION_COORDS

    items = _iter_fleet_tracker_items(_RSS_URLS)
    if not items:
        logger.warning("USNI fleet-tracker: no parseable RSS items")
        return {}

    # Pick the most recent by parsed pubDate. Items without a parseable
    # date fall to the back of the list.
    items.sort(
        key=lambda it: it["pub_date"] or datetime(1970, 1, 1, tzinfo=timezone.utc),
        reverse=True,
    )
    latest = items[0]

    pub_dt: datetime | None = latest["pub_date"]
    pub_iso = pub_dt.isoformat() if pub_dt else ""
    pub_human = pub_dt.strftime("%b %d, %Y") if pub_dt else "unknown date"

    body = latest["body"]
    if not body:
        logger.warning("USNI fleet-tracker: latest item has empty body")
        return {}

    positions: dict[str, dict] = {}
    for hull, info in carrier_registry.items():
        # Build name variants we'll try in the body.
        full_name = info["name"]                       # "USS Gerald R. Ford (CVN-78)"
        without_hull = full_name.split("(")[0].strip() # "USS Gerald R. Ford"
        last_word = without_hull.split()[-1]            # "Ford"
        ship_only = without_hull[4:]                    # "Gerald R. Ford"

        # Variants ordered most-specific first.
        variants: list[str] = []
        for v in (without_hull, f"USS {ship_only}", ship_only, last_word):
            if v and v not in variants and len(v) >= 4:
                variants.append(v)

        phrase = _extract_region_for_carrier(body, variants, hull)
        if not phrase:
            continue
        resolved = _resolve_region_phrase(phrase)
        if not resolved:
            logger.debug(
                "USNI: %s region phrase %r did not match any known region",
                hull, phrase,
            )
            continue
        canonical_key, display_phrase = resolved
        coords = region_coords.get(canonical_key)
        if not coords:
            continue

        positions[hull] = {
            "lat": coords[0],
            "lng": coords[1],
            "heading": 0,
            "desc": f"{display_phrase.title()} (USNI {pub_human})",
            "source": f"USNI News Fleet & Marine Tracker ({pub_human})",
            "source_url": latest["link"],
            "position_source_at": pub_iso,
            "position_confidence": "recent",
        }

    if positions:
        logger.info(
            "USNI fleet-tracker: parsed %d/%d carrier positions from %s",
            len(positions), len(carrier_registry), latest["link"],
        )
    else:
        logger.warning(
            "USNI fleet-tracker: latest article %s yielded zero parseable carriers",
            latest["link"],
        )
    return positions

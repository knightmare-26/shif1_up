"""Where driver names come from.

FastF1's names aren't reliable enough to be the source: it shortens some ("Kimi Antonelli" where
the standings say "Andrea Kimi Antonelli"), and a stand-in who drives someone else's car in FP1
gets that driver's first/last name (Mari Boya stored as "Sergio Perez"). So:

- anyone who has raced: Jolpica's season driver list, the same source as the standings, so a
  driver is named the same on every page;
- anyone else (FP1-only stand-ins): OpenF1's full_name for the three-letter code, which is right
  even where its first/last name fields carry the car owner's.

Both are free, keyless APIs; any failure just means no name from that source.
"""
import logging
import time
import unicodedata
from typing import Dict, Optional

import httpx

logger = logging.getLogger(__name__)

JOLPICA = "https://api.jolpi.ca/ergast/f1"
OPENF1 = "https://api.openf1.org/v1"


def same_name(a: Optional[str], b: Optional[str]) -> bool:
    """Accent- and case-insensitive ("Nico Hulkenberg" is "Nico Hülkenberg")."""
    def key(s):
        return "".join(c for c in unicodedata.normalize("NFD", s or "") if not unicodedata.combining(c)).casefold().strip()
    return bool(a) and bool(b) and key(a) == key(b)


def tidy_full_name(name: str) -> str:
    """OpenF1 writes surnames in capitals ("Mari BOYA"); keep mixed-case words as they are."""
    return " ".join(w.capitalize() if w.isupper() and len(w) > 1 else w for w in name.split())


def jolpica_names(year: int, client: Optional[httpx.Client] = None) -> Dict[str, str]:
    """{"ANT": "Andrea Kimi Antonelli", ...} for the drivers who raced in `year`."""
    own = client is None
    client = client or httpx.Client(timeout=20)
    try:
        r = client.get(f"{JOLPICA}/{year}/drivers.json", params={"limit": 100})
        r.raise_for_status()
        drivers = r.json()["MRData"]["DriverTable"]["Drivers"]
        return {d["code"].upper(): f"{d.get('givenName', '')} {d.get('familyName', '')}".strip()
                for d in drivers if d.get("code")}
    except Exception as exc:
        logger.warning("jolpica driver names for %s: %s", year, exc)
        return {}
    finally:
        if own:
            client.close()


def openf1_name(code: str, client: Optional[httpx.Client] = None) -> Optional[str]:
    """Full name OpenF1 has for a three-letter code (latest session it appears in)."""
    own = client is None
    client = client or httpx.Client(timeout=20)
    try:
        for attempt in range(4):   # the free tier rate-limits bursts (HTTP 429)
            r = client.get(f"{OPENF1}/drivers", params={"name_acronym": code.upper()})
            if r.status_code != 429:
                break
            time.sleep(2 ** attempt)
        if r.status_code != 200:
            return None
        rows = [row for row in r.json() if isinstance(row, dict) and row.get("full_name")]
        if not rows:
            return None
        latest = max(rows, key=lambda row: row.get("session_key") or 0)
        return tidy_full_name(latest["full_name"])
    except Exception as exc:
        logger.warning("openf1 name for %s: %s", code, exc)
        return None
    finally:
        if own:
            client.close()

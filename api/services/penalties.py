"""
Penalties and other stewards' decisions for a finished session, read from its race-control messages
(OpenF1's `race_control`, free for finished sessions from 2023 — the same feed FastF1 reads), e.g.

    FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 44 (HAM) - SPEEDING IN THE PIT LANE (15:39:17)
    FIA STEWARDS: PENALTY SERVED - STOP-AND-GO PENALTY FOR CAR 43 (COL) - STARTING PROCEDURE INFRINGEMENT
    CAR 27 (HUL) TIME 1:23.646 DELETED - TRACK LIMITS AT TURN 3 LAP 5 15:40:03
    CAR 11 (PER) TIME 1:31.451 WILL BE REINSTATED

Only the messages worth keeping are stored (`relevant`), and they're parsed when served, so a better
parser never needs a refetch. Grid penalties for engine parts, or carried over from an earlier race,
are published as FIA documents rather than race control: those show as a driver starting behind
where they qualified (`grid_changes`). Decisions taken after the session (a post-race time penalty)
don't always reach race control either; the results refresh still picks up their effect.
"""
import re
from typing import Any, Dict, Iterable, List, Optional

KEEP = re.compile(r"STEWARDS|DELETED|REINSTATED|BLACK AND WHITE|DISQUALIF", re.I)
FIELDS = ("date", "lap_number", "category", "flag", "message", "driver_number")

_CAR = r"CAR (?P<number>\d+) \((?P<code>[A-Z]{3})\)"
# What a decision is, checked in this order (a stop-and-go message can mention seconds too).
DECISIONS = [
    ("time", re.compile(r"(?P<seconds>\d+) SECOND TIME PENALTY FOR " + _CAR)),
    ("stop_go", re.compile(r"(?:(?P<seconds>\d+) SECOND )?STOP[- ]AND[- ]GO PENALTY FOR " + _CAR)),
    ("drive_through", re.compile(r"DRIVE[- ]THROUGH PENALTY FOR " + _CAR)),
    ("grid", re.compile(r"(?P<places>\d+) PLACE GRID PENALTY FOR " + _CAR)),
    ("disqualified", re.compile(r"DISQUALIFICATION FOR " + _CAR + r"|" + _CAR.replace("number", "n2").replace("code", "c2")
                                + r".{0,40}?\bDISQUALIFIED")),
    ("black_and_white", re.compile(r"BLACK AND WHITE FLAG FOR " + _CAR)),
    ("reprimand", re.compile(r"REPRIMAND FOR " + _CAR)),
    ("warning", re.compile(r"WARNING FOR " + _CAR)),
]
# Penalties that change a result (time, drive-through, stop-go, disqualification) or the next grid.
PENALTIES = {"time", "stop_go", "drive_through", "grid", "disqualified"}
# A deleted lap time: "CAR 55 (SAI) TIME 1:25.773 DELETED - …", "CAR 44 (HAM) LAP DELETED - …", and
# (Canada 2026) "CAR LEC TIME 1:36.518 DELETED - …" / "CAR LAW TIME DELETED - …" without the number.
_ANY_CAR = r"CAR (?:(?P<number>\d+) \((?P<code>[A-Z]{3})\)|(?P<bare>[A-Z]{3}))"
DELETED = re.compile(_ANY_CAR + r" (?:TIME (?P<time>[\d:.]+) |TIME |LAP )?DELETED - (?P<reason>.+)")
# ... and one given back after review: "CAR 11 (PER) TIME 1:31.451 WILL BE REINSTATED", "CAR 55 (SAI) LAP 1 WILL BE REINSTATED".
REINSTATED = re.compile(_ANY_CAR + r" (?:TIME (?P<time>[\d:.]+)|LAP (?P<lap>\d+)) WILL BE REINSTATED")
_ASIDES = re.compile(r"\s*\([^)]*\)")
_CLOCK = re.compile(r"\s*\(?\d{1,2}:\d{2}:\d{2}\)?\s*$")
_LAP = re.compile(r"\s+LAP (\d+)\b")
_ACRONYMS = re.compile(r"\b(vsc|sc|drs|fia|pu|ers)\b", re.I)


def relevant(messages: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The race-control messages worth storing: the stewards', flags for a driver, deleted laps."""
    return [{k: m.get(k) for k in FIELDS} for m in messages if KEEP.search(str(m.get("message") or ""))]


def _sentence(text: str) -> str:
    """"SPEEDING IN THE PIT LANE (15:39:17)" -> "Speeding in the pit lane"."""
    text = _CLOCK.sub("", text).strip(" -")
    return _ACRONYMS.sub(lambda m: m.group().upper(), text.capitalize()) if text else ""


def _car(match: "re.Match") -> tuple:
    groups = match.groupdict()
    return groups.get("code") or groups.get("c2"), int(groups.get("number") or groups.get("n2"))


def parse(messages: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """{decisions, deleted_laps, drivers}: every decision in order, every deleted lap time, and a
    summary per driver code (the badges on the results)."""
    decisions: List[Dict[str, Any]] = []
    deleted: List[Dict[str, Any]] = []
    for m in messages:
        text = str(m.get("message") or "").upper()
        lap = m.get("lap_number")

        found = REINSTATED.search(text)
        if found:
            code = found["code"] or found["bare"]
            mine = [d for d in deleted if d["driver"] == code]
            match = next((d for d in reversed(mine) if (found["time"] and d["time"] == found["time"])
                          or (found["lap"] and d["lap"] == int(found["lap"]))), mine[-1] if mine else None)
            if match:
                deleted.remove(match)
            continue

        found = DELETED.search(text)
        if found:
            reason = _ASIDES.sub("", found["reason"])            # "(NEXT LAP)", "(Q1)", "(PIT)"
            lap_in_text = _LAP.search(reason)
            deleted.append({"driver": found["code"] or found["bare"],
                            "number": int(found["number"]) if found["number"] else None,
                            "time": found["time"],
                            "lap": int(lap_in_text.group(1)) if lap_in_text else lap,
                            "reason": _sentence(_LAP.split(reason)[0])})
            continue

        served = "PENALTY SERVED" in text
        for kind, pattern in DECISIONS:
            found = pattern.search(text)
            if not found:
                continue
            code, number = _car(found)
            if served:
                # The penalty given earlier is now served: mark it, don't count it twice.
                earlier = next((d for d in reversed(decisions)
                                if d["driver"] == code and d["kind"] == kind and not d["served"]), None)
                if earlier:
                    earlier["served"] = True
                break
            rest = text[found.end():]
            groups = found.groupdict()
            decisions.append({
                "driver": code, "number": number, "kind": kind,
                "seconds": int(groups["seconds"]) if groups.get("seconds") else None,
                "places": int(groups["places"]) if groups.get("places") else None,
                "reason": _sentence(rest[3:]) if rest.startswith(" - ") else "",
                "lap": lap, "date": m.get("date"), "served": False,
                "message": str(m.get("message") or ""),
            })
            break

    drivers: Dict[str, Dict[str, Any]] = {}

    def entry(code: str) -> Dict[str, Any]:
        return drivers.setdefault(code, {"time_penalty_seconds": 0, "penalties": [], "warnings": 0,
                                         "reprimands": 0, "black_and_white": False, "disqualified": False,
                                         "deleted_laps": 0})

    for d in decisions:
        e = entry(d["driver"])
        if d["kind"] == "time":
            e["time_penalty_seconds"] += d["seconds"] or 0
        if d["kind"] in PENALTIES:
            e["penalties"].append(d["kind"])
        e["warnings"] += d["kind"] == "warning"
        e["reprimands"] += d["kind"] == "reprimand"
        e["black_and_white"] |= d["kind"] == "black_and_white"
        e["disqualified"] |= d["kind"] == "disqualified"
    for d in deleted:
        entry(d["driver"])["deleted_laps"] += 1
    return {"decisions": decisions, "deleted_laps": deleted, "drivers": drivers}


def grid_changes(race_rows: List[Dict[str, Any]], qualifying_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Drivers who started behind where they qualified (a grid penalty), or from the pit lane:
    {code: {qualified, started, pit_lane}}. A driver moved *up* by others' penalties isn't listed."""
    ranked = sorted((r for r in qualifying_rows if r.get("position") is not None), key=lambda r: float(r["position"]))
    qualified: Dict[str, int] = {}
    for i, r in enumerate(ranked, start=1):
        qualified.setdefault(str(r["driver_id"]).upper(), i)
    out: Dict[str, Dict[str, Any]] = {}
    for r in race_rows:
        code, grid = str(r.get("driver_id") or "").upper(), r.get("grid")
        if not code or grid is None or code not in qualified:
            continue
        try:
            grid = int(float(grid))
        except (TypeError, ValueError):
            continue
        if grid == 0 or grid > qualified[code]:
            out[code] = {"qualified": qualified[code], "started": grid or None, "pit_lane": grid == 0}
    return out

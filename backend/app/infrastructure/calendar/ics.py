"""Leitor de calendário ICS (o "endereço secreto" do Google, Outlook ou iCloud).

Sem login nem OAuth: a pessoa cola a URL e o DroidNote só lê. Interpreta o
necessário para "quais reuniões vêm aí": VEVENT, fuso (TZID), recorrência
(RRULE/EXDATE/RECURRENCE-ID), participantes e cancelamentos. Eventos de dia
inteiro ficam de fora — não são reuniões.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, tzinfo
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from dateutil.rrule import rruleset, rrulestr

CACHE_SECONDS = 600
MAX_BYTES = 8 * 1024 * 1024

# Outlook/Exchange exporta o nome de fuso do Windows; os mais comuns.
WINDOWS_ZONES = {
    "E. South America Standard Time": "America/Sao_Paulo",
    "SA Eastern Standard Time": "America/Fortaleza",
    "Argentina Standard Time": "America/Argentina/Buenos_Aires",
    "Pacific SA Standard Time": "America/Santiago",
    "SA Pacific Standard Time": "America/Bogota",
    "Central Standard Time (Mexico)": "America/Mexico_City",
    "Eastern Standard Time": "America/New_York",
    "Central Standard Time": "America/Chicago",
    "Mountain Standard Time": "America/Denver",
    "Pacific Standard Time": "America/Los_Angeles",
    "GMT Standard Time": "Europe/London",
    "W. Europe Standard Time": "Europe/Berlin",
    "Romance Standard Time": "Europe/Paris",
    "Central Europe Standard Time": "Europe/Budapest",
    "Central European Standard Time": "Europe/Warsaw",
    "GTB Standard Time": "Europe/Bucharest",
    "Russian Standard Time": "Europe/Moscow",
    "UTC": "UTC",
}


class CalendarError(RuntimeError):
    pass


@dataclass(frozen=True)
class Attendee:
    name: str
    email: str | None = None


@dataclass(frozen=True)
class CalendarEvent:
    uid: str
    title: str
    start: datetime
    end: datetime
    location: str | None = None
    attendees: tuple[Attendee, ...] = field(default_factory=tuple)


@dataclass
class _Raw:
    props: list[tuple[str, dict[str, str], str]] = field(default_factory=list)

    def first(self, name: str) -> tuple[dict[str, str], str] | None:
        for key, params, value in self.props:
            if key == name:
                return params, value
        return None

    def all(self, name: str) -> list[tuple[dict[str, str], str]]:
        return [(params, value) for key, params, value in self.props if key == name]


def normalize_url(raw: str) -> str:
    url = raw.strip()
    if url.lower().startswith("webcal://"):
        url = "https://" + url[len("webcal://") :]
    if not re.match(r"^https?://", url, re.IGNORECASE):
        raise CalendarError("invalid_url")
    host = urlparse(url).hostname or ""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and not ip.is_global:
        raise CalendarError("blocked_url")
    return url


def _reject_private(host: str) -> None:
    """Recusa loopback, link-local e rede privada, inclusive depois de redirect.

    # ponytail: resolve no gancho da requisição. Janela entre o DNS e o
    # connect se o nome mudar de IP; transporte que pina o IP fecha isso.
    """
    if not host:
        raise CalendarError("blocked_url")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise CalendarError("unreachable") from exc
        addresses = [ipaddress.ip_address(item[4][0]) for item in infos]
    if not addresses or any(not ip.is_global for ip in addresses):
        raise CalendarError("blocked_url")


def _guard_request(request: httpx.Request) -> None:
    _reject_private(request.url.host)


class IcsCalendar:
    """Baixa e guarda o ICS por alguns minutos; o parse é puro e testável."""

    def __init__(self, *, timeout: float = 15.0) -> None:
        self._timeout = timeout
        self._cache: dict[str, tuple[float, str]] = {}

    async def fetch(self, url: str, *, force: bool = False) -> str:
        target = normalize_url(url)
        cached = self._cache.get(target)
        if cached and not force and time.monotonic() - cached[0] < CACHE_SECONDS:
            return cached[1]
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=True,
                event_hooks={"request": [_guard_request]},
            ) as client:
                response = await client.get(target, headers={"Accept": "text/calendar, */*"})
        except httpx.HTTPError as exc:
            raise CalendarError("unreachable") from exc
        if response.status_code >= 400:
            raise CalendarError(f"http_{response.status_code}")
        if len(response.content) > MAX_BYTES:
            raise CalendarError("too_large")
        text = response.text
        if "BEGIN:VCALENDAR" not in text[:4096].upper():
            raise CalendarError("not_ics")
        self._cache[target] = (time.monotonic(), text)
        return text

    async def upcoming(
        self, url: str, *, now: datetime | None = None, hours: float = 36, back_hours: float = 1
    ) -> list[CalendarEvent]:
        text = await self.fetch(url)
        moment = now or datetime.now(tz=UTC)
        return expand(parse_events(text), moment - timedelta(hours=back_hours), moment + timedelta(hours=hours))


def unfold(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line[:1] in (" ", "\t") and lines:
            lines[-1] += line[1:]
        elif line:
            lines.append(line)
    return lines


def split_property(line: str) -> tuple[str, dict[str, str], str]:
    quoted = False
    cut = -1
    for index, ch in enumerate(line):
        if ch == '"':
            quoted = not quoted
        elif ch == ":" and not quoted:
            cut = index
            break
    if cut < 0:
        return line.upper(), {}, ""
    head, value = line[:cut], line[cut + 1 :]
    parts = head.split(";")
    params: dict[str, str] = {}
    for part in parts[1:]:
        if "=" in part:
            key, raw = part.split("=", 1)
            params[key.upper()] = raw.strip('"')
    return parts[0].upper(), params, value


def parse_events(text: str) -> list[_Raw]:
    events: list[_Raw] = []
    current: _Raw | None = None
    depth = 0
    for line in unfold(text):
        name, params, value = split_property(line)
        if name == "BEGIN" and value.upper() == "VEVENT":
            current = _Raw()
            depth = 0
            continue
        if current is None:
            continue
        if name == "BEGIN":
            depth += 1  # VALARM e afins: ignora o miolo
            continue
        if name == "END":
            if value.upper() == "VEVENT" and depth == 0:
                events.append(current)
                current = None
            else:
                depth = max(0, depth - 1)
            continue
        if depth == 0:
            current.props.append((name, params, value))
    return events


def _zone(tzid: str | None) -> tzinfo | None:
    if not tzid:
        return None
    candidates = [WINDOWS_ZONES.get(tzid, tzid)]
    pieces = tzid.strip("/").split("/")
    if len(pieces) >= 2:
        candidates.append("/".join(pieces[-2:]))
    for name in candidates:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            continue
    return None


def parse_dt(value: str, params: dict[str, str]) -> datetime | date | None:
    raw = value.strip()
    try:
        if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", raw):
            return datetime.strptime(raw[:8], "%Y%m%d").date()
        if raw.endswith("Z"):
            return datetime.strptime(raw[:-1], "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
        naive = datetime.strptime(raw[:15], "%Y%m%dT%H%M%S")
    except ValueError:
        return None
    zone = _zone(params.get("TZID"))
    if zone is not None:
        return naive.replace(tzinfo=zone)
    return naive.astimezone()  # hora "flutuante": a do PC


def parse_duration(value: str) -> timedelta | None:
    match = re.fullmatch(r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", value.strip())
    if not match:
        return None
    sign, weeks, days, hours, minutes, seconds = match.groups()
    delta = timedelta(
        weeks=int(weeks or 0),
        days=int(days or 0),
        hours=int(hours or 0),
        minutes=int(minutes or 0),
        seconds=int(seconds or 0),
    )
    return -delta if sign == "-" else delta


def unescape(value: str) -> str:
    return (
        value.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")
    ).strip()


def _attendees(raw: _Raw) -> tuple[Attendee, ...]:
    people: list[Attendee] = []
    seen: set[str] = set()
    for params, value in raw.all("ATTENDEE") + raw.all("ORGANIZER"):
        email = value[7:] if value.lower().startswith("mailto:") else None
        name = unescape(params.get("CN", "")) or (email.split("@")[0] if email else "")
        key = (email or name).lower()
        if not name or key in seen:
            continue
        seen.add(key)
        people.append(Attendee(name=name, email=email))
    return tuple(people)


def _instant(value: datetime | date | None) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    return None


def expand(raws: list[_Raw], window_start: datetime, window_end: datetime) -> list[CalendarEvent]:
    overrides: dict[tuple[str, datetime], _Raw] = {}
    masters: list[_Raw] = []
    for raw in raws:
        rid = raw.first("RECURRENCE-ID")
        uid = (raw.first("UID") or ({}, ""))[1]
        if rid is not None:
            instant = _instant(parse_dt(rid[1], rid[0]))
            if instant is not None:
                overrides[(uid, instant)] = raw
                continue
        masters.append(raw)

    events: list[CalendarEvent] = []
    for raw in masters:
        uid = (raw.first("UID") or ({}, ""))[1]
        start_prop = raw.first("DTSTART")
        if start_prop is None:
            continue
        start = parse_dt(start_prop[1], start_prop[0])
        if not isinstance(start, datetime):
            continue  # dia inteiro
        length = _length(raw, start)
        rule = raw.first("RRULE")
        if rule is None:
            starts = [start]
        else:
            starts = _occurrences(raw, start, rule[1], window_start - length, window_end)
        for occurrence in starts:
            override = overrides.pop((uid, occurrence.astimezone(UTC)), None)
            if override is not None:
                moved = override.first("DTSTART")
                moved_start = parse_dt(moved[1], moved[0]) if moved else None
                if isinstance(moved_start, datetime):
                    event = _build(override, uid, moved_start, _length(override, moved_start))
                else:
                    event = _build(override, uid, occurrence, length)
            else:
                event = _build(raw, uid, occurrence, length)
            if event and event.end > window_start and event.start < window_end:
                events.append(event)
    for (uid, _), raw in overrides.items():
        start_prop = raw.first("DTSTART")
        start = parse_dt(start_prop[1], start_prop[0]) if start_prop else None
        if isinstance(start, datetime):
            event = _build(raw, uid, start, _length(raw, start))
            if event and event.end > window_start and event.start < window_end:
                events.append(event)
    events.sort(key=lambda item: item.start)
    return events


def _length(raw: _Raw, start: datetime) -> timedelta:
    end_prop = raw.first("DTEND")
    if end_prop is not None:
        end = parse_dt(end_prop[1], end_prop[0])
        if isinstance(end, datetime):
            return max(end - start, timedelta(0))
    duration = raw.first("DURATION")
    if duration is not None:
        parsed = parse_duration(duration[1])
        if parsed is not None:
            return parsed
    return timedelta(minutes=30)


def _occurrences(raw: _Raw, start: datetime, rule: str, after: datetime, before: datetime) -> list[datetime]:
    try:
        rules = rruleset()
        rules.rrule(rrulestr(_fit_until(rule, start), dtstart=start))
        for params, value in raw.all("EXDATE"):
            for piece in value.split(","):
                excluded = parse_dt(piece, params)
                if isinstance(excluded, datetime):
                    rules.exdate(excluded.astimezone(start.tzinfo))
        return list(rules.between(after.astimezone(start.tzinfo), before.astimezone(start.tzinfo), inc=True))
    except (ValueError, TypeError):
        return [start]


def _fit_until(rule: str, start: datetime) -> str:
    """dateutil exige UNTIL com o mesmo tipo de fuso que DTSTART."""

    def fix(match: re.Match[str]) -> str:
        value = match.group(1)
        if len(value) == 8:
            value += "T235959"
        if not value.endswith("Z"):
            local = datetime.strptime(value[:15], "%Y%m%dT%H%M%S").replace(tzinfo=start.tzinfo)
            value = local.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        return f"UNTIL={value}"

    return re.sub(r"UNTIL=([0-9TZ]+)", fix, rule)


def _build(raw: _Raw, uid: str, start: datetime, length: timedelta) -> CalendarEvent | None:
    status = raw.first("STATUS")
    if status is not None and status[1].strip().upper() == "CANCELLED":
        return None
    summary = raw.first("SUMMARY")
    location = raw.first("LOCATION")
    return CalendarEvent(
        uid=uid,
        title=unescape(summary[1]) if summary else "",
        start=start.astimezone(UTC),
        end=(start + length).astimezone(UTC),
        location=unescape(location[1]) or None if location else None,
        attendees=_attendees(raw),
    )

"""robots.txt, fetched once per origin, with RFC 9309 status handling (one deliberate exception).

  2xx            -> parse and obey
  404/410/other 4xx -> "unavailable": no rules, crawling allowed (RFC 9309 s.2.3.1.3)
  401/403        -> treated as DISALLOW ALL. RFC 9309 would allow, but a site that refuses even
                    robots.txt to an anonymous client is refusing; we read that as a no.
  5xx / network  -> "unreachable": disallow all (RFC 9309 s.2.3.1.4)

Crawl-delay is honoured when present (it is not in RFC 9309, but it is the site's stated wish).
"""

from __future__ import annotations

import urllib.error
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urlsplit

from . import USER_AGENT, USER_AGENT_TOKEN


@dataclass
class RobotsVerdict:
    allowed: bool
    reason: str               # parsed | unavailable_4xx | refused_401_403 | unreachable
    crawl_delay: float | None = None


class Robots:
    def __init__(self, timeout: float = 20.0, opener=None):
        self.timeout = timeout
        self._by_origin: dict[str, tuple[urllib.robotparser.RobotFileParser | None, str]] = {}
        self._open = opener or urllib.request.urlopen

    @staticmethod
    def origin(url: str) -> str:
        p = urlsplit(url)
        return f"{p.scheme}://{p.netloc}"

    def _load(self, origin: str) -> tuple[urllib.robotparser.RobotFileParser | None, str]:
        if origin in self._by_origin:
            return self._by_origin[origin]
        req = urllib.request.Request(origin + "/robots.txt", headers={"User-Agent": USER_AGENT})
        rp = urllib.robotparser.RobotFileParser()
        try:
            with self._open(req, timeout=self.timeout) as r:
                body = r.read(512_000).decode("utf-8", "replace")
            rp.parse(body.splitlines())
            state = (rp, "parsed")
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                state = (None, "refused_401_403")
            elif 400 <= e.code < 500:
                state = (None, "unavailable_4xx")
            else:
                state = (None, "unreachable")
        except (urllib.error.URLError, OSError, ValueError):
            state = (None, "unreachable")
        self._by_origin[origin] = state
        return state

    def check(self, url: str) -> RobotsVerdict:
        rp, state = self._load(self.origin(url))
        if state == "unavailable_4xx":
            return RobotsVerdict(True, state)
        if rp is None:
            return RobotsVerdict(False, state)
        delay = rp.crawl_delay(USER_AGENT_TOKEN)
        return RobotsVerdict(rp.can_fetch(USER_AGENT_TOKEN, url), state,
                             float(delay) if delay is not None else None)

    def sitemaps(self, url: str) -> list[str]:
        rp, _ = self._load(self.origin(url))
        return list(rp.site_maps() or []) if rp is not None else []

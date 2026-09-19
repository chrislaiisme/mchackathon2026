"""Fashion data collection that stops where a site says no.

Two kinds of source, both producing the same `Record`:

  * `web.WebSource`        -- public pages a site allows automated clients to fetch (robots.txt),
                             with rate limiting, a disk cache, de-duplication and error logging;
  * `instagram`            -- Instagram through the official Graph API, or through data the account
                             owner exported themselves. Instagram's own robots.txt disallows every
                             crawler ("User-agent: * / Disallow: /") and states that automated
                             collection is prohibited without written permission, so there is no
                             page-scraping path for it here.

What the crawler treats as a stop signal, never as an obstacle to route around: robots.txt
disallow, HTTP 401/403/407/451, a redirect to a login page, a CAPTCHA or bot-challenge page, and
rate limiting that persists after honouring Retry-After. The source is stopped and the reason is
written to the run report.

Fields a page does not provide in structured form (JSON-LD, OpenGraph, microdata) are left empty.
Nothing is inferred from free text. See docs/crawler.md.

    python -m engine02.crawl --config scripts/crawl_sources.example.toml
    python -m engine02.crawl --url https://shop.example/products/x --max-pages 1
"""

from .records import Record  # noqa: F401

USER_AGENT_TOKEN = "IntentWeaveFashionCrawler"
USER_AGENT = (f"{USER_AGENT_TOKEN}/0.1 (+https://github.com/chrislaiisme/mchackathon2026; "
              "non-commercial research; honours robots.txt)")

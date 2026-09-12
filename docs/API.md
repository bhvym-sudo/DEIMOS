# DEIMOS Service API

The browser connects directly to two independently running services. Next.js does not create or supervise either process.

## Go engine gateway — port 8787

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Service and crawler health |
| GET | `/api/crawler/stats` | Investigation crawler totals |
| GET | `/api/phobos-search/stats` | PHOBOS Search index, queue and rating totals |
| GET | `/api/phobos-search/search?q=term&limit=50` | Search only the PHOBOS Search database |
| GET | `/api/crawler/config` | Read persistent crawler settings |
| PUT | `/api/crawler/config` | Validate and save settings; crawler must be stopped |
| GET | `/api/crawler/status` | Runtime workers, pages and failures |
| POST | `/api/crawler/start` | Start in-process Go workers |
| POST | `/api/crawler/stop` | Cancel workers and active requests |
| POST | `/api/crawler/retry-failed` | Return failed queue entries to pending |
| GET/POST/DELETE | `/api/crawler/seeds` | Manage Crawler sources |
| GET/PUT | `/api/phobos-search/config` | Read or save PHOBOS Search settings |
| GET | `/api/phobos-search/status` | PHOBOS Search runtime state |
| POST | `/api/phobos-search/start` | Start PHOBOS Search workers |
| POST | `/api/phobos-search/stop` | Stop PHOBOS Search workers |
| GET/POST/DELETE | `/api/phobos-search/seeds` | Manage PHOBOS Search discovery sources |
| GET | `/ws` | Live crawler events and heartbeats |

Crawler settings/sources use `config/crawler.json` and `config/crawler-seeds.json`. PHOBOS Search uses `config/phobos-search.json` and `config/phobos-search-seeds.json`.

## Python intelligence service — port 8001

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Intelligence service health |
| GET | `/api/stats` | Analysis and entity totals |
| GET | `/api/stats/{engine}` | Totals for `crawler` or `phobos-search` |
| GET | `/api/reports` | Threat-analysis records |
| GET | `/api/entities` | Extracted NER records |
| GET | `/api/profiles` | Existing investigation profiles |
| GET | `/ws` | Live analysis database events |

The next Python milestone will add a managed analysis job API. The current service exposes existing PHOBOS analysis results without being launched by Next.js.

## Browser configuration

Set these values in `frontend/.env.local` before building or starting Next.js:

```text
NEXT_PUBLIC_GO_API_URL=http://127.0.0.1:8787
NEXT_PUBLIC_GO_WS_URL=ws://127.0.0.1:8787/ws
NEXT_PUBLIC_PYTHON_API_URL=http://127.0.0.1:8001
NEXT_PUBLIC_PYTHON_WS_URL=ws://127.0.0.1:8001/ws
```

For Docker, these must be browser-reachable host addresses. Docker-only service names such as `go-service` cannot be resolved by a user's browser.

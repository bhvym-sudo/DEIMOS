# DEIMOS Architecture

DEIMOS is split into three independently deployable services while the original `phobos/` prototype remains intact.

## Runtime layout

```text
Browser (Next.js :3000)
        | REST + WebSocket
        v
Go gateway (:8787) ----+--> Crawler --------> crawler.db
                       +--> PHOBOS Search --> phobos_search.db
                                  |
Python AI (:8001) ---------------+--> ratings, NER and threat records in each source database
```

## Service responsibilities

| Service | Responsibility |
| --- | --- |
| Next.js | Crawler controls, PHOBOS Search home/results/settings, intelligence views and live events |
| Go | Two independent crawler managers, namespaced APIs, continuous PHOBOS Search indexing and WebSockets |
| Python | Watches both engine databases and stores each page's rating and analysis with its source data |
| PHOBOS | Preserved legacy crawler, configuration and SQLite data used during migration |

## Current engine split

Crawler is the investigation-oriented engine and is started manually. PHOBOS Search is a separate continuous background indexer that auto-starts with the Go gateway. Each engine has independent configuration, sources, queue, lifecycle and SQLite storage.

1. Stabilize the collection and search APIs.
2. Move seed and crawler configuration into the Go service.
3. Convert the Python processor into queued model workers.
4. Add the relationship graph and evidence ledger.
5. Add authentication, case isolation and role-based access.

## Safety boundary

Collection must be limited to legally authorized sources. Automated attribution is presented as an evidence-backed hypothesis with confidence and provenance, never as a final identity claim.

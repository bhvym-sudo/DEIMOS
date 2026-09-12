# DEIMOS

**Dark-web Entity Identification, Mapping and OSINT System**

DEIMOS is a root-level web application for authorized dark-web intelligence collection, search and AI-assisted analysis. The existing `phobos/` folder remains intact as the legacy crawler and analysis prototype while its capabilities are migrated behind service APIs.

## Workspace

- `frontend/` — Next.js investigation interface
- `backend/` — native Go crawler, REST API, live events and index search
- `ai_service/` — Python intelligence and model service
- `docs/ARCHITECTURE.md` — architecture and migration notes
- `phobos/` — preserved original prototype

## Run locally

Install dependencies once:

```powershell
cd frontend
npm install
cd ..
python -m pip install -r ai_service/requirements.txt
cd backend
go mod download
cd ..
```

Start all three services:

```powershell
.\scripts\dev.ps1
```

Then open `http://127.0.0.1:3000`. The Go service listens on port `8787` and the Python service on `8001`.

## Run with Docker

Docker runs Tor, the native Go crawler/search API, the Python intelligence API, the PHOBOS analysis worker and Next.js as separate containers:

```powershell
docker compose up --build -d
docker compose ps
```

Open `http://127.0.0.1:3000`. Follow startup logs with:

```powershell
docker compose logs -f
```

Stop the stack without deleting databases or named volumes:

```powershell
docker compose down
```

The existing databases in `phobos/databases/` are bind-mounted so local and Docker runs use the same indexed data. Do not run the local Go crawler or local analysis processor at the same time as their Docker containers.

## Current prototype slice

- Independent Crawler and PHOBOS Search engines
- Separate `crawler.db` and `phobos_search.db` storage
- Independent settings, seeds, queues and start/stop APIs
- Continuously running PHOBOS Search indexer with home statistics and results view
- AI ratings and NER written back to the database that supplied each page
- Persistent Tor and crawler configuration
- Threat intelligence records
- AI pipeline status
- WebSocket event stream

DEIMOS is intended for lawful, authorized investigations. Model output is a confidence-weighted lead that must be reviewed against its supporting evidence.

The Next.js application never launches Go, Python or an executable. Each service is an independent process and the browser connects to their configured HTTP and WebSocket addresses. The legacy `phobos-crawler.exe` is no longer used by the new backend.

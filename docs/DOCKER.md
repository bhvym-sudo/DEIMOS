# Running DEIMOS with Docker Desktop

## One-time Windows setup

DEIMOS uses Linux containers. Docker Desktop must use the WSL 2 engine.

1. Open **PowerShell as Administrator**.
2. Run `wsl --install`.
3. Restart Windows when requested.
4. Open Docker Desktop and wait until it reports that the engine is running.
5. In Docker Desktop, enable **Settings → General → Use the WSL 2 based engine**.
6. Open a new PowerShell window and run `docker version` and `docker compose version`.

If `docker` is not recognized after Docker Desktop is installed, restart Windows. If it remains unavailable, repair/reinstall Docker Desktop and ensure its CLI is added to PATH.

## Start DEIMOS

From the repository root:

```powershell
cd E:\projects\BPD\DEIMOS
docker compose up --build -d
docker compose ps
```

The first build is large because it downloads Go, Node.js, Python NLP packages and the spaCy English model.

Open `http://127.0.0.1:3000` after every service reports healthy/running.

## Operations

```powershell
# Follow all logs
docker compose logs -f

# Follow one service
docker compose logs -f go-service
docker compose logs -f analysis-worker

# Restart the stack
docker compose restart

# Rebuild after source changes
docker compose up --build -d

# Stop containers while preserving data
docker compose down
```

Do not use `docker compose down -v` unless you intentionally want to remove Docker-managed Tor state, crawler configuration and generated analysis reports. The SQLite databases remain in `phobos/databases/` because they are bind-mounted from the host.

## Services

| Container | Role | Host endpoint |
| --- | --- | --- |
| `frontend` | Next.js interface | `http://127.0.0.1:3000` |
| `go-service` | Native crawler, index and search API | `http://127.0.0.1:8787` |
| `python-api` | Intelligence API and WebSocket | `http://127.0.0.1:8001` |
| `analysis-worker` | PHOBOS NER/threat processor | Internal only |
| `tor` | Isolated SOCKS5 proxy | `127.0.0.1:9050` |

Next.js does not start the other services. Compose independently starts and supervises every container.

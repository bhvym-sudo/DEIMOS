# PHOBOS Intelligence Platform

Dark web intelligence gathering and database leak detection system with geopolitical risk analysis.

## Project Structure

```
PHOBOS/
├── analysis/
│   ├── leak_detector.py          Database leak pattern detection
│   ├── processor.py               NER and threat analysis
│   └── __init__.py
├── config_files/
│   ├── crawler_config.json        Crawler configuration
│   ├── intelligence_data_new.json Keywords and threat patterns
│   ├── profiles.json              Person profiles database
│   ├── seed_urls_dark.json        Dark web seed URLs
│   └── tor_config.json            Tor configuration
├── databases/
│   ├── phobos_index.db           Go crawler index
│   └── phobos_analysis.db        Python analysis results
├── phobos-crawler/               Go crawler (20 concurrent workers)
│   ├── main.go
│   ├── parser.go
│   ├── database.go
│   └── tor.go
├── scripts/
│   ├── analyzer.py               IntelligenceAnalyzer
│   ├── person_profiler.py        Person intelligence
│   └── utils/
│       ├── crawler_manager.py    Python-Go bridge
│       ├── run_processor.py      Processor launcher
│       └── migrate_leak_detection.py
├── templates/                    Flask HTML templates
├── web/
│   ├── app.py                   Threat reports (port 7788)
│   └── search_app.py            Search engine (port 8080)
├── gui.py                       Main PyQt5 application
└── main.py                      Application entry point
```

## Core Features

### 1. Dark Web Crawler
- **Technology**: Go with 20 concurrent workers
- **Target**: .onion dark web URLs
- **Proxy**: Tor SOCKS5 (127.0.0.1:9050)
- **Features**:
  - Proper URL resolution (net/url package)
  - Per-page deduplication
  - Media file filtering
  - SQLite storage with WAL mode

### 2. NER & Threat Analysis
- **Engine**: spaCy (en_core_web_sm)
- **Extracts**: Persons, Organizations, Locations, Dates, Money
- **Threat Scoring**: IntelligenceAnalyzer neural network
- **Database**: phobos_analysis.db

### 3. Database Leak Detection (NEW)
- **Pattern Matching**: .sql, .csv, .db files, dump/breach/leaked keywords
- **PII Detection**: Aadhaar, PAN, emails, phones, credit cards
- **Geopolitical Analysis**: India vs Pakistan/Bangladesh
- **Risk Classification**:
  - `CRITICAL_THREAT`: Indian government/military data leaked
  - `HIGH_THREAT`: Indian sensitive PII leaked
  - `STRATEGIC_ADVANTAGE`: Enemy country government data
  - `INTELLIGENCE_VALUE`: Enemy country sensitive data
  - `INTERNATIONAL_CONCERN`: Other countries critical leaks

### 4. PyQt5 GUI
- **HOME**: Control panel + system/crawler/Tor logs
- **SEED URLs**: Dark web URL management
- **INTELLIGENCE DATA**: Keywords and threat samples
- **REPORT BRIEFING**: 4 subtabs (Search Engine, Threat Reports, Crawled URLs, Portal Reports)
- **DATABASE LEAKS**: Leak monitoring with filters
- **PROFILING**: Person intelligence

## Setup

### Prerequisites
```powershell
Python 3.8+
Go 1.18+
Tor Browser (for SOCKS5 proxy)
```

### Installation
```powershell
pip install -r requirements.txt
python -m spacy download en_core_web_sm
cd phobos-crawler
go build -o phobos-crawler.exe
```

### Database Migration
```powershell
python scripts\utils\migrate_leak_detection.py
```

## Usage

### Start GUI
```powershell
python gui.py
```

### Configuration
1. Add seed URLs in SEED URLs tab
2. Configure crawler (depth, workers, delays)
3. Click START CRAWLER

### Leak Detection Workflow
1. Crawler discovers pages → Go saves to phobos_index.db
2. processor.py analyzes text → NER + threat scoring + leak detection
3. Detected leaks saved with geopolitical risk
4. GUI displays in DATABASE LEAKS tab with filters

### Monitor Leaks
- **Filter by Risk**: CRITICAL_THREAT, HIGH_THREAT, STRATEGIC_ADVANTAGE
- **Filter by Country**: India, Pakistan, Bangladesh
- **Filter by Threat**: Yes (threat to India), No (advantage)
- **Export**: CSV export for reporting

## Leak Detection Logic

### India (THREAT)
- **CRITICAL_THREAT**: Government/military + high sensitivity
- **HIGH_THREAT**: PII/financial + high/critical sensitivity
- **MEDIUM_THREAT**: Other Indian data

### Pakistan/Bangladesh (ADVANTAGE)
- **STRATEGIC_ADVANTAGE**: Government/military + critical sensitivity
- **INTELLIGENCE_VALUE**: PII/financial + high sensitivity
- **MONITOR**: Other data

### Indicators
- Database files: .sql, .db, .csv, .sqlite
- Keywords: dump, breach, leaked, stolen, credentials, backup
- PII patterns: Aadhaar (12 digits), PAN (5 letters + 4 digits + 1 letter), emails, phones
- Country markers: .gov.in, .gov.pk, .gov.bd, city names, document types

## Process Management

### Startup
- Cleanup orphaned processes (taskkill)
- Initialize Tor connection
- Load configurations

### Stop Crawler
1. Write stop command to config.json
2. Wait 2 seconds
3. QProcess.terminate()
4. QProcess.kill()
5. taskkill /F /IM phobos-crawler.exe

### Shutdown
- Kill Go crawler
- Terminate Flask apps
- Stop Tor process

## Architecture

```
PyQt5 GUI
  ↓ (atomic config.json writes)
Go Crawler (polls every 2s)
  ↓ (20 workers continuously crawl)
SQLite (phobos_index.db)
  ↓ (processor.py reads unprocessed)
NER + Threat Analysis + Leak Detection
  ↓ (saves results)
SQLite (phobos_analysis.db)
  ↓ (Flask queries)
Web Dashboard (ports 7788, 8080)
```

## Configuration Files

### crawler_config.json
```json
{
  "seed_urls": ["http://example.onion"],
  "depth_limit": 3,
  "download_delay": 1,
  "concurrent_workers": 20
}
```

### intelligence_data_new.json
```json
{
  "keywords": ["weapon", "drug", "exploit"],
  "threat_levels": {...},
  "entities": {...}
}
```

## Database Schema

### phobos_index.db (Go)
- pages: URL, HTML, content, crawled_at
- tokens: Word index
- token_documents: Inverted index
- links: URL relationships
- crawl_queue: Pending/processing/completed

### phobos_analysis.db (Python)
- ner_results: Extracted entities
- threat_analysis: Threat scores + leak detection fields
- processing_status: Processing tracking

## Troubleshooting

### Crawler Stuck
- Check Tor connection (127.0.0.1:9050)
- Verify seed URLs are valid .onion addresses
- Check CRAWLER LOGS tab for errors

### No Leaks Detected
- Verify processor is running: `python scripts\utils\run_processor.py`
- Check if pages contain database-related keywords
- Review leak_detector.py patterns

### Import Errors
- Ensure all __init__.py files exist
- Run from project root
- Check Python path includes PHOBOS/

### Process Orphaning
- GUI automatically cleans up on startup
- Manual: `taskkill /F /IM phobos-crawler.exe`

## Performance

- **Crawler**: 20 concurrent workers, ~100-200 pages/hour (Tor limited)
- **Processor**: ~10-20 pages/second (CPU limited)
- **Database**: SQLite WAL mode, 25 max connections
- **Memory**: ~500MB (GUI + crawler + processor)

## Security Notes

- All traffic routed through Tor
- No credentials stored in plaintext
- Database files contain sensitive intelligence data
- Regularly backup databases/ folder
- Use in isolated environment

## Future Enhancements

- [ ] Real-time alerts for CRITICAL_THREAT leaks
- [ ] Telegram/email notifications
- [ ] Advanced NER models (transformers)
- [ ] Distributed crawler support
- [ ] Graph visualization of leak networks
- [ ] Automated geopolitical risk scoring
- [ ] Integration with external threat intelligence feeds

## License

Internal use only. Sensitive intelligence platform.

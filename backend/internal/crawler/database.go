package crawler

import (
	"database/sql"
	"encoding/json"
	"path/filepath"
	"strings"
	"time"

	_ "github.com/mattn/go-sqlite3"
)

type crawlDatabase struct{ db *sql.DB }

type task struct {
	ID    int64
	URL   string
	Depth int
}

type page struct {
	URL, Title, Content, HTML, Domain string
	Depth                             int
	Links                             []string
	StatusCode                        int
	ContentType, Server, PoweredBy    string
	Headers                           map[string]string
	TLS                               *tlsMetadata
	StatusPages                       []map[string]any
}

func openDatabase(path string) (*crawlDatabase, error) {
	absolute, err := filepath.Abs(path)
	if err != nil {
		return nil, err
	}
	dsn := "file:" + strings.ReplaceAll(absolute, "\\", "/") + "?cache=shared&mode=rwc&_journal_mode=WAL&_busy_timeout=10000"
	db, err := sql.Open("sqlite3", dsn)
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(8)
	statements := []string{
		`CREATE TABLE IF NOT EXISTS pages (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE NOT NULL, title TEXT, content TEXT, html_content TEXT, domain TEXT, content_hash TEXT, content_length INTEGER, inbound_links INTEGER DEFAULT 0, outbound_links INTEGER DEFAULT 0, page_rank REAL DEFAULT 0.0, crawl_depth INTEGER DEFAULT 0, crawled_at TIMESTAMP, last_modified TIMESTAMP, status_code INTEGER DEFAULT 200, is_active BOOLEAN DEFAULT 1, crawl_count INTEGER DEFAULT 0, threat_score REAL, threat_level TEXT, analyzed_at TIMESTAMP, content_type TEXT, server_banner TEXT, powered_by TEXT, response_headers TEXT, tls_subject TEXT, tls_issuer TEXT, tls_serial TEXT, tls_not_before TEXT, tls_not_after TEXT, tls_dns_names TEXT, tls_fingerprint_sha256 TEXT, status_pages TEXT, recon_scanned_at TIMESTAMP)`,
		`CREATE TABLE IF NOT EXISTS crawl_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE NOT NULL, depth INTEGER DEFAULT 0, priority REAL DEFAULT 1.0, discovered_from TEXT, retry_count INTEGER DEFAULT 0, status TEXT DEFAULT 'pending', added_at TIMESTAMP, last_attempt TIMESTAMP)`,
		`CREATE INDEX IF NOT EXISTS idx_pages_url ON pages(url)`,
		`CREATE INDEX IF NOT EXISTS idx_queue_status ON crawl_queue(status)`,
	}
	for _, statement := range statements {
		if _, err := db.Exec(statement); err != nil {
			_ = db.Close()
			return nil, err
		}
	}
	for _, migration := range []string{
		`ALTER TABLE pages ADD COLUMN threat_score REAL`,
		`ALTER TABLE pages ADD COLUMN threat_level TEXT`,
		`ALTER TABLE pages ADD COLUMN analyzed_at TIMESTAMP`,
		`ALTER TABLE pages ADD COLUMN content_type TEXT`, `ALTER TABLE pages ADD COLUMN server_banner TEXT`, `ALTER TABLE pages ADD COLUMN powered_by TEXT`, `ALTER TABLE pages ADD COLUMN response_headers TEXT`,
		`ALTER TABLE pages ADD COLUMN tls_subject TEXT`, `ALTER TABLE pages ADD COLUMN tls_issuer TEXT`, `ALTER TABLE pages ADD COLUMN tls_serial TEXT`, `ALTER TABLE pages ADD COLUMN tls_not_before TEXT`, `ALTER TABLE pages ADD COLUMN tls_not_after TEXT`, `ALTER TABLE pages ADD COLUMN tls_dns_names TEXT`, `ALTER TABLE pages ADD COLUMN tls_fingerprint_sha256 TEXT`, `ALTER TABLE pages ADD COLUMN status_pages TEXT`, `ALTER TABLE pages ADD COLUMN recon_scanned_at TIMESTAMP`,
	} {
		_, _ = db.Exec(migration)
	}
	_, _ = db.Exec(`UPDATE crawl_queue SET status = 'pending' WHERE status = 'processing'`)
	return &crawlDatabase{db: db}, nil
}

func (d *crawlDatabase) addTask(rawURL string, depth int, from string, recrawl bool) error {
	query := `INSERT OR IGNORE INTO crawl_queue (url, depth, discovered_from, added_at, status) VALUES (?, ?, ?, ?, 'pending')`
	if recrawl {
		query = `INSERT INTO crawl_queue (url, depth, discovered_from, added_at, status) VALUES (?, ?, ?, ?, 'pending') ON CONFLICT(url) DO UPDATE SET depth=excluded.depth, discovered_from=excluded.discovered_from, added_at=excluded.added_at, status=CASE WHEN crawl_queue.status='processing' THEN 'processing' ELSE 'pending' END`
	}
	_, err := d.db.Exec(query, rawURL, depth, from, time.Now().UTC())
	return err
}

func (d *crawlDatabase) claimTask() (*task, error) {
	tx, err := d.db.Begin()
	if err != nil {
		return nil, err
	}
	defer tx.Rollback()
	row := tx.QueryRow(`SELECT id, url, depth FROM crawl_queue WHERE status = 'pending' ORDER BY priority DESC, depth ASC LIMIT 1`)
	var item task
	if err := row.Scan(&item.ID, &item.URL, &item.Depth); err != nil {
		if err == sql.ErrNoRows {
			return nil, nil
		}
		return nil, err
	}
	result, err := tx.Exec(`UPDATE crawl_queue SET status = 'processing', last_attempt = ? WHERE id = ? AND status = 'pending'`, time.Now().UTC(), item.ID)
	if err != nil {
		return nil, err
	}
	changed, _ := result.RowsAffected()
	if changed != 1 {
		return nil, nil
	}
	if err := tx.Commit(); err != nil {
		return nil, err
	}
	return &item, nil
}

func (d *crawlDatabase) savePage(value page) error {
	headers, _ := json.Marshal(value.Headers)
	statusPages, _ := json.Marshal(value.StatusPages)
	var subject, issuer, serial, notBefore, notAfter, dnsNames, fingerprint string
	if value.TLS != nil {
		subject, issuer, serial, notBefore, notAfter, fingerprint = value.TLS.Subject, value.TLS.Issuer, value.TLS.Serial, value.TLS.NotBefore, value.TLS.NotAfter, value.TLS.Fingerprint
		encoded, _ := json.Marshal(value.TLS.DNSNames)
		dnsNames = string(encoded)
	}
	_, err := d.db.Exec(`INSERT INTO pages (url,title,content,html_content,domain,content_length,outbound_links,crawl_depth,crawled_at,status_code,is_active,crawl_count,content_type,server_banner,powered_by,response_headers,tls_subject,tls_issuer,tls_serial,tls_not_before,tls_not_after,tls_dns_names,tls_fingerprint_sha256,status_pages,recon_scanned_at) VALUES (?,?,?,?,?,?,?,?,?,?,1,1,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET title=excluded.title,content=excluded.content,html_content=excluded.html_content,domain=excluded.domain,content_length=excluded.content_length,outbound_links=excluded.outbound_links,crawl_depth=excluded.crawl_depth,crawled_at=excluded.crawled_at,status_code=excluded.status_code,is_active=1,crawl_count=pages.crawl_count+1,content_type=excluded.content_type,server_banner=excluded.server_banner,powered_by=excluded.powered_by,response_headers=excluded.response_headers,tls_subject=excluded.tls_subject,tls_issuer=excluded.tls_issuer,tls_serial=excluded.tls_serial,tls_not_before=excluded.tls_not_before,tls_not_after=excluded.tls_not_after,tls_dns_names=excluded.tls_dns_names,tls_fingerprint_sha256=excluded.tls_fingerprint_sha256,status_pages=excluded.status_pages,recon_scanned_at=excluded.recon_scanned_at`, value.URL, value.Title, value.Content, value.HTML, value.Domain, len(value.Content), len(value.Links), value.Depth, time.Now().UTC(), value.StatusCode, value.ContentType, value.Server, value.PoweredBy, string(headers), subject, issuer, serial, notBefore, notAfter, dnsNames, fingerprint, string(statusPages), time.Now().UTC())
	return err
}

func (d *crawlDatabase) complete(id int64) {
	_, _ = d.db.Exec(`UPDATE crawl_queue SET status = 'completed' WHERE id = ?`, id)
}
func (d *crawlDatabase) fail(id int64) {
	_, _ = d.db.Exec(`UPDATE crawl_queue SET status = 'failed', retry_count = retry_count + 1 WHERE id = ?`, id)
}
func (d *crawlDatabase) retryFailed() (int64, error) {
	result, err := d.db.Exec(`UPDATE crawl_queue SET status = 'pending' WHERE status = 'failed'`)
	if err != nil {
		return 0, err
	}
	return result.RowsAffected()
}
func (d *crawlDatabase) counts() (indexed, pending, failed int) {
	_ = d.db.QueryRow(`SELECT COUNT(*) FROM pages WHERE is_active = 1`).Scan(&indexed)
	_ = d.db.QueryRow(`SELECT COUNT(*) FROM crawl_queue WHERE status = 'pending'`).Scan(&pending)
	_ = d.db.QueryRow(`SELECT COUNT(*) FROM crawl_queue WHERE status = 'failed'`).Scan(&failed)
	return
}
func (d *crawlDatabase) close() error { return d.db.Close() }

package crawler

import (
	"database/sql"
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
		`CREATE TABLE IF NOT EXISTS pages (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE NOT NULL, title TEXT, content TEXT, html_content TEXT, domain TEXT, content_hash TEXT, content_length INTEGER, inbound_links INTEGER DEFAULT 0, outbound_links INTEGER DEFAULT 0, page_rank REAL DEFAULT 0.0, crawl_depth INTEGER DEFAULT 0, crawled_at TIMESTAMP, last_modified TIMESTAMP, status_code INTEGER DEFAULT 200, is_active BOOLEAN DEFAULT 1, crawl_count INTEGER DEFAULT 0, threat_score REAL, threat_level TEXT, analyzed_at TIMESTAMP)`,
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
	_, err := d.db.Exec(`INSERT INTO pages (url, title, content, html_content, domain, content_length, outbound_links, crawl_depth, crawled_at, status_code, is_active, crawl_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 200, 1, 1) ON CONFLICT(url) DO UPDATE SET title=excluded.title, content=excluded.content, html_content=excluded.html_content, domain=excluded.domain, content_length=excluded.content_length, outbound_links=excluded.outbound_links, crawl_depth=excluded.crawl_depth, crawled_at=excluded.crawled_at, status_code=200, is_active=1, crawl_count=pages.crawl_count+1`, value.URL, value.Title, value.Content, value.HTML, value.Domain, len(value.Content), len(value.Links), value.Depth, time.Now().UTC())
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

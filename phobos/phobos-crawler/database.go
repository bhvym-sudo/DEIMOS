package main

import (
	"database/sql"
	"time"

	_ "github.com/mattn/go-sqlite3"
)

type Database struct {
	db *sql.DB
}

type CrawlTask struct {
	ID             int
	URL            string
	Depth          int
	DiscoveredFrom string
}

type PageData struct {
	URL           string
	Title         string
	Content       string
	HTMLContent   string
	Domain        string
	ContentLength int
	CrawlDepth    int
	OutboundLinks []string
}

func initDatabase(dbPath string) (*Database, error) {
	db, err := sql.Open("sqlite3", dbPath+"?cache=shared&mode=rwc&_journal_mode=WAL&_busy_timeout=5000")
	if err != nil {
		return nil, err
	}

	db.SetMaxOpenConns(25)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(time.Hour)

	_, err = db.Exec(`
		CREATE TABLE IF NOT EXISTS pages (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			url TEXT UNIQUE NOT NULL,
			title TEXT,
			content TEXT,
			html_content TEXT,
			domain TEXT,
			content_hash TEXT,
			content_length INTEGER,
			inbound_links INTEGER DEFAULT 0,
			outbound_links INTEGER DEFAULT 0,
			page_rank REAL DEFAULT 0.0,
			crawl_depth INTEGER DEFAULT 0,
			crawled_at TIMESTAMP,
			last_modified TIMESTAMP,
			status_code INTEGER DEFAULT 200,
			is_active BOOLEAN DEFAULT 1,
			crawl_count INTEGER DEFAULT 0
		)
	`)
	if err != nil {
		return nil, err
	}

	_, err = db.Exec(`
		CREATE TABLE IF NOT EXISTS tokens (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			token TEXT UNIQUE NOT NULL,
			document_freq INTEGER DEFAULT 0,
			idf REAL DEFAULT 0.0
		)
	`)
	if err != nil {
		return nil, err
	}

	_, err = db.Exec(`
		CREATE TABLE IF NOT EXISTS token_documents (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			token_id INTEGER,
			page_id INTEGER,
			term_freq INTEGER,
			positions TEXT,
			field TEXT,
			FOREIGN KEY(token_id) REFERENCES tokens(id),
			FOREIGN KEY(page_id) REFERENCES pages(id),
			UNIQUE(token_id, page_id, field)
		)
	`)
	if err != nil {
		return nil, err
	}

	_, err = db.Exec(`
		CREATE TABLE IF NOT EXISTS links (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			source_id INTEGER,
			target_url TEXT,
			target_id INTEGER,
			anchor_text TEXT,
			discovered_at TIMESTAMP,
			FOREIGN KEY(source_id) REFERENCES pages(id)
		)
	`)
	if err != nil {
		return nil, err
	}

	_, err = db.Exec(`
		CREATE TABLE IF NOT EXISTS crawl_queue (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			url TEXT UNIQUE NOT NULL,
			depth INTEGER DEFAULT 0,
			priority REAL DEFAULT 1.0,
			discovered_from TEXT,
			retry_count INTEGER DEFAULT 0,
			status TEXT DEFAULT 'pending',
			added_at TIMESTAMP,
			last_attempt TIMESTAMP
		)
	`)
	if err != nil {
		return nil, err
	}

	_, err = db.Exec(`CREATE INDEX IF NOT EXISTS idx_pages_url ON pages(url)`)
	_, err = db.Exec(`CREATE INDEX IF NOT EXISTS idx_pages_crawled_at ON pages(crawled_at)`)
	_, err = db.Exec(`CREATE INDEX IF NOT EXISTS idx_queue_status ON crawl_queue(status)`)
	_, err = db.Exec(`CREATE INDEX IF NOT EXISTS idx_queue_priority ON crawl_queue(priority DESC)`)

	return &Database{db: db}, nil
}

func (d *Database) SavePage(page PageData) int64 {
	result, err := d.db.Exec(`
		INSERT OR REPLACE INTO pages 
		(url, title, content, html_content, domain, content_length, crawl_depth, crawled_at, status_code)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
	`, page.URL, page.Title, page.Content, page.HTMLContent, page.Domain,
		page.ContentLength, page.CrawlDepth, time.Now(), 200)

	if err != nil {
		return 0
	}

	id, _ := result.LastInsertId()
	return id
}

func (d *Database) AddTask(url string, depth int, discoveredFrom string) {
	d.db.Exec(`
		INSERT OR IGNORE INTO crawl_queue (url, depth, discovered_from, added_at)
		VALUES (?, ?, ?, ?)
	`, url, depth, discoveredFrom, time.Now())
}

func (d *Database) GetPendingTasks(limit int) []CrawlTask {
	rows, err := d.db.Query(`
		SELECT id, url, depth, discovered_from
		FROM crawl_queue
		WHERE status = 'pending'
		ORDER BY priority DESC, depth ASC
		LIMIT ?
	`, limit)

	if err != nil {
		return []CrawlTask{}
	}
	defer rows.Close()

	var tasks []CrawlTask
	for rows.Next() {
		var task CrawlTask
		rows.Scan(&task.ID, &task.URL, &task.Depth, &task.DiscoveredFrom)
		tasks = append(tasks, task)
	}

	for _, task := range tasks {
		d.db.Exec(`UPDATE crawl_queue SET status = 'processing', last_attempt = ? WHERE id = ?`,
			time.Now(), task.ID)
	}

	return tasks
}

func (d *Database) MarkTaskCompleted(taskID int) {
	d.db.Exec(`UPDATE crawl_queue SET status = 'completed' WHERE id = ?`, taskID)
}

func (d *Database) MarkTaskFailed(taskID int) {
	d.db.Exec(`
		UPDATE crawl_queue 
		SET status = 'failed', retry_count = retry_count + 1 
		WHERE id = ?
	`, taskID)
}

func (d *Database) CountIndexedPages() int {
	var count int
	d.db.QueryRow(`SELECT COUNT(*) FROM pages WHERE is_active = 1`).Scan(&count)
	return count
}

func (d *Database) GetQueueSize() int {
	var count int
	d.db.QueryRow(`SELECT COUNT(*) FROM crawl_queue WHERE status = 'pending'`).Scan(&count)
	return count
}

func (d *Database) Close() {
	d.db.Close()
}

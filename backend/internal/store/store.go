package store

import (
	"database/sql"
	"fmt"
	"math"
	"path/filepath"
	"strings"

	_ "github.com/mattn/go-sqlite3"
)

type Store struct {
	index    *sql.DB
	analysis *sql.DB
}

type Stats struct {
	IndexedPages     int  `json:"indexed_pages"`
	QueuedPages      int  `json:"queued_pages"`
	AnalyzedPages    int  `json:"analyzed_pages"`
	CriticalFindings int  `json:"critical_findings"`
	HighFindings     int  `json:"high_findings"`
	EntitiesFound    int  `json:"entities_found"`
	CrawlerRunning   bool `json:"crawler_running"`
	TorConfigured    bool `json:"tor_configured"`
}

type SearchResult struct {
	ID        int     `json:"id"`
	URL       string  `json:"url"`
	Title     string  `json:"title"`
	Snippet   string  `json:"snippet"`
	Domain    string  `json:"domain"`
	CrawledAt string  `json:"crawled_at"`
	Score     float64 `json:"score"`
}

func sqliteReadOnly(path string) (*sql.DB, error) {
	abs, err := filepath.Abs(path)
	if err != nil {
		return nil, err
	}
	dsn := "file:" + strings.ReplaceAll(abs, "\\", "/") + "?mode=rwc&_busy_timeout=10000"
	db, err := sql.Open("sqlite3", dsn)
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(4)
	if err := db.Ping(); err != nil {
		_ = db.Close()
		return nil, err
	}
	return db, nil
}

func Open(indexPath, analysisPath string) (*Store, error) {
	index, err := sqliteReadOnly(indexPath)
	if err != nil {
		return nil, fmt.Errorf("open index database: %w", err)
	}
	analysis, err := sqliteReadOnly(analysisPath)
	if err != nil {
		_ = index.Close()
		return nil, fmt.Errorf("open analysis database: %w", err)
	}
	for _, statement := range []string{
		`CREATE TABLE IF NOT EXISTS pages (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE NOT NULL, title TEXT, content TEXT, html_content TEXT, domain TEXT, content_hash TEXT, content_length INTEGER, inbound_links INTEGER DEFAULT 0, outbound_links INTEGER DEFAULT 0, page_rank REAL DEFAULT 0.0, crawl_depth INTEGER DEFAULT 0, crawled_at TIMESTAMP, last_modified TIMESTAMP, status_code INTEGER DEFAULT 200, is_active BOOLEAN DEFAULT 1, crawl_count INTEGER DEFAULT 0, threat_score REAL, threat_level TEXT, analyzed_at TIMESTAMP)`,
		`CREATE TABLE IF NOT EXISTS crawl_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE NOT NULL, depth INTEGER DEFAULT 0, priority REAL DEFAULT 1.0, discovered_from TEXT, retry_count INTEGER DEFAULT 0, status TEXT DEFAULT 'pending', added_at TIMESTAMP, last_attempt TIMESTAMP)`,
	} {
		if _, err := index.Exec(statement); err != nil {
			index.Close()
			analysis.Close()
			return nil, err
		}
	}
	for _, migration := range []string{
		`ALTER TABLE pages ADD COLUMN threat_score REAL`,
		`ALTER TABLE pages ADD COLUMN threat_level TEXT`,
		`ALTER TABLE pages ADD COLUMN analyzed_at TIMESTAMP`,
	} {
		_, _ = index.Exec(migration)
	}
	return &Store{index: index, analysis: analysis}, nil
}

func (s *Store) Close() { _ = s.index.Close(); _ = s.analysis.Close() }

func count(db *sql.DB, query string, args ...any) int {
	var value int
	if err := db.QueryRow(query, args...).Scan(&value); err != nil {
		return 0
	}
	return value
}

func (s *Store) Stats(crawlerRunning, torConfigured bool) Stats {
	return Stats{
		IndexedPages:     count(s.index, "SELECT COUNT(*) FROM pages WHERE is_active = 1"),
		QueuedPages:      count(s.index, "SELECT COUNT(*) FROM crawl_queue WHERE status = 'pending'"),
		AnalyzedPages:    count(s.analysis, "SELECT COUNT(*) FROM threat_analysis"),
		CriticalFindings: count(s.analysis, "SELECT COUNT(*) FROM threat_analysis WHERE risk_classification = 'CRITICAL_THREAT' OR threat_level = 'CRITICAL'"),
		HighFindings:     count(s.analysis, "SELECT COUNT(*) FROM threat_analysis WHERE risk_classification = 'HIGH_THREAT' OR threat_level = 'HIGH'"),
		EntitiesFound:    count(s.analysis, "SELECT COUNT(*) FROM ner_results"),
		CrawlerRunning:   crawlerRunning,
		TorConfigured:    torConfigured,
	}
}

func (s *Store) Search(query string, limit int) ([]SearchResult, error) {
	query = strings.TrimSpace(query)
	if query == "" {
		return []SearchResult{}, nil
	}
	if limit < 1 || limit > 100 {
		limit = 50
	}
	pattern := "%" + query + "%"
	rows, err := s.index.Query(`
		SELECT id, url, COALESCE(title, ''), COALESCE(content, ''), COALESCE(domain, ''), COALESCE(crawled_at, CURRENT_TIMESTAMP),
			CASE WHEN title LIKE ? THEN 1.0 WHEN url LIKE ? THEN 0.85 ELSE 0.65 END AS relevance
		FROM pages
		WHERE is_active = 1 AND (title LIKE ? OR url LIKE ? OR content LIKE ?)
		ORDER BY relevance DESC, crawled_at DESC LIMIT ?`, pattern, pattern, pattern, pattern, pattern, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	results := make([]SearchResult, 0)
	for rows.Next() {
		var result SearchResult
		var content string
		if err := rows.Scan(&result.ID, &result.URL, &result.Title, &content, &result.Domain, &result.CrawledAt, &result.Score); err != nil {
			return nil, err
		}
		result.Snippet = snippet(content, query, 240)
		result.Score = math.Min(math.Max(result.Score, 0), 1)
		results = append(results, result)
	}
	return results, rows.Err()
}

func snippet(content, query string, size int) string {
	content = strings.Join(strings.Fields(content), " ")
	if len(content) <= size {
		return content
	}
	lower, needle := strings.ToLower(content), strings.ToLower(query)
	index := strings.Index(lower, needle)
	if index < 0 {
		return content[:size] + "…"
	}
	start := index - size/3
	if start < 0 {
		start = 0
	}
	end := start + size
	if end > len(content) {
		end = len(content)
	}
	prefix, suffix := "", ""
	if start > 0 {
		prefix = "…"
	}
	if end < len(content) {
		suffix = "…"
	}
	return prefix + content[start:end] + suffix
}

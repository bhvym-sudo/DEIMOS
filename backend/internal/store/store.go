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

type PageRecord struct {
	ID              int     `json:"id"`
	URL             string  `json:"url"`
	Title           string  `json:"title"`
	Domain          string  `json:"domain"`
	Content         string  `json:"content,omitempty"`
	HTML            string  `json:"html,omitempty"`
	ContentLength   int     `json:"content_length"`
	CrawlDepth      int     `json:"crawl_depth"`
	CrawledAt       string  `json:"crawled_at"`
	StatusCode      int     `json:"status_code"`
	CrawlCount      int     `json:"crawl_count"`
	ThreatScore     float64 `json:"threat_score"`
	ThreatLevel     string  `json:"threat_level"`
	AnalyzedAt      string  `json:"analyzed_at"`
	ContentType     string  `json:"content_type"`
	ServerBanner    string  `json:"server_banner"`
	PoweredBy       string  `json:"powered_by"`
	ResponseHeaders string  `json:"response_headers"`
	TLSSubject      string  `json:"tls_subject"`
	TLSIssuer       string  `json:"tls_issuer"`
	TLSSerial       string  `json:"tls_serial"`
	TLSNotBefore    string  `json:"tls_not_before"`
	TLSNotAfter     string  `json:"tls_not_after"`
	TLSDNSNames     string  `json:"tls_dns_names"`
	TLSFingerprint  string  `json:"tls_fingerprint_sha256"`
	StatusPages     string  `json:"status_pages"`
	ReconScannedAt  string  `json:"recon_scanned_at"`
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
		`CREATE TABLE IF NOT EXISTS pages (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE NOT NULL, title TEXT, content TEXT, html_content TEXT, domain TEXT, content_hash TEXT, content_length INTEGER, inbound_links INTEGER DEFAULT 0, outbound_links INTEGER DEFAULT 0, page_rank REAL DEFAULT 0.0, crawl_depth INTEGER DEFAULT 0, crawled_at TIMESTAMP, last_modified TIMESTAMP, status_code INTEGER DEFAULT 200, is_active BOOLEAN DEFAULT 1, crawl_count INTEGER DEFAULT 0, threat_score REAL, threat_level TEXT, analyzed_at TIMESTAMP, content_type TEXT, server_banner TEXT, powered_by TEXT, response_headers TEXT, tls_subject TEXT, tls_issuer TEXT, tls_serial TEXT, tls_not_before TEXT, tls_not_after TEXT, tls_dns_names TEXT, tls_fingerprint_sha256 TEXT, status_pages TEXT, recon_scanned_at TIMESTAMP)`,
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
		`ALTER TABLE pages ADD COLUMN content_type TEXT`, `ALTER TABLE pages ADD COLUMN server_banner TEXT`, `ALTER TABLE pages ADD COLUMN powered_by TEXT`, `ALTER TABLE pages ADD COLUMN response_headers TEXT`,
		`ALTER TABLE pages ADD COLUMN tls_subject TEXT`, `ALTER TABLE pages ADD COLUMN tls_issuer TEXT`, `ALTER TABLE pages ADD COLUMN tls_serial TEXT`, `ALTER TABLE pages ADD COLUMN tls_not_before TEXT`, `ALTER TABLE pages ADD COLUMN tls_not_after TEXT`, `ALTER TABLE pages ADD COLUMN tls_dns_names TEXT`, `ALTER TABLE pages ADD COLUMN tls_fingerprint_sha256 TEXT`, `ALTER TABLE pages ADD COLUMN status_pages TEXT`, `ALTER TABLE pages ADD COLUMN recon_scanned_at TIMESTAMP`,
	} {
		_, _ = index.Exec(migration)
	}
	return &Store{index: index, analysis: analysis}, nil
}

func (s *Store) Pages(query string, limit, offset int) ([]PageRecord, int, error) {
	if limit < 1 || limit > 200 {
		limit = 50
	}
	if offset < 0 {
		offset = 0
	}
	pattern := "%" + strings.TrimSpace(query) + "%"
	where := "WHERE is_active = 1"
	args := []any{}
	if strings.TrimSpace(query) != "" {
		where += " AND (url LIKE ? OR title LIKE ? OR domain LIKE ?)"
		args = append(args, pattern, pattern, pattern)
	}
	var total int
	if err := s.index.QueryRow("SELECT COUNT(*) FROM pages "+where, args...).Scan(&total); err != nil {
		return nil, 0, err
	}
	args = append(args, limit, offset)
	rows, err := s.index.Query(`SELECT id,url,COALESCE(title,''),COALESCE(domain,''),COALESCE(content_length,0),COALESCE(crawl_depth,0),COALESCE(crawled_at,''),COALESCE(status_code,0),COALESCE(crawl_count,0),COALESCE(threat_score,0),COALESCE(threat_level,''),COALESCE(analyzed_at,''),COALESCE(content_type,''),COALESCE(server_banner,''),COALESCE(powered_by,''),COALESCE(tls_subject,''),COALESCE(tls_issuer,''),COALESCE(tls_fingerprint_sha256,''),COALESCE(recon_scanned_at,'') FROM pages `+where+` ORDER BY crawled_at DESC LIMIT ? OFFSET ?`, args...)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()
	records := []PageRecord{}
	for rows.Next() {
		var p PageRecord
		if err := rows.Scan(&p.ID, &p.URL, &p.Title, &p.Domain, &p.ContentLength, &p.CrawlDepth, &p.CrawledAt, &p.StatusCode, &p.CrawlCount, &p.ThreatScore, &p.ThreatLevel, &p.AnalyzedAt, &p.ContentType, &p.ServerBanner, &p.PoweredBy, &p.TLSSubject, &p.TLSIssuer, &p.TLSFingerprint, &p.ReconScannedAt); err != nil {
			return nil, 0, err
		}
		records = append(records, p)
	}
	return records, total, rows.Err()
}

func (s *Store) Page(id int) (PageRecord, error) {
	var p PageRecord
	err := s.index.QueryRow(`SELECT id,url,COALESCE(title,''),COALESCE(domain,''),COALESCE(content,''),COALESCE(html_content,''),COALESCE(content_length,0),COALESCE(crawl_depth,0),COALESCE(crawled_at,''),COALESCE(status_code,0),COALESCE(crawl_count,0),COALESCE(threat_score,0),COALESCE(threat_level,''),COALESCE(analyzed_at,''),COALESCE(content_type,''),COALESCE(server_banner,''),COALESCE(powered_by,''),COALESCE(response_headers,''),COALESCE(tls_subject,''),COALESCE(tls_issuer,''),COALESCE(tls_serial,''),COALESCE(tls_not_before,''),COALESCE(tls_not_after,''),COALESCE(tls_dns_names,''),COALESCE(tls_fingerprint_sha256,''),COALESCE(status_pages,''),COALESCE(recon_scanned_at,'') FROM pages WHERE id=?`, id).Scan(&p.ID, &p.URL, &p.Title, &p.Domain, &p.Content, &p.HTML, &p.ContentLength, &p.CrawlDepth, &p.CrawledAt, &p.StatusCode, &p.CrawlCount, &p.ThreatScore, &p.ThreatLevel, &p.AnalyzedAt, &p.ContentType, &p.ServerBanner, &p.PoweredBy, &p.ResponseHeaders, &p.TLSSubject, &p.TLSIssuer, &p.TLSSerial, &p.TLSNotBefore, &p.TLSNotAfter, &p.TLSDNSNames, &p.TLSFingerprint, &p.StatusPages, &p.ReconScannedAt)
	return p, err
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

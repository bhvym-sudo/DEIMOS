package crawler

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"deimos/internal/events"
)

type Status struct {
	Running       bool   `json:"running"`
	StartedAt     string `json:"started_at,omitempty"`
	PagesCrawled  int64  `json:"pages_crawled"`
	RequestErrors int64  `json:"request_errors"`
	ActiveWorkers int    `json:"active_workers"`
	IndexedPages  int    `json:"indexed_pages"`
	PendingURLs   int    `json:"pending_urls"`
	FailedURLs    int    `json:"failed_urls"`
}

type Manager struct {
	mu       sync.RWMutex
	claimMu  sync.Mutex
	store    *ConfigStore
	hub      *events.Hub
	config   Config
	running  bool
	started  time.Time
	cancel   context.CancelFunc
	done     chan struct{}
	database *crawlDatabase
	client   *http.Client
	pages    atomic.Int64
	failures atomic.Int64
	workers  atomic.Int32
	name     string
}

func NewManager(root string, hub *events.Hub) (*Manager, error) {
	return NewEngineManager(root, hub, "Crawler", "crawler.json", "crawler-seeds.json", DefaultConfigFor("phobos/databases/crawler.db", "DEIMOS-Crawler/0.3 (+authorized-security-research)"))
}

func NewEngineManager(root string, hub *events.Hub, name, configFile, seedsFile string, defaults Config) (*Manager, error) {
	store := NewConfigStoreForEngine(root, configFile, seedsFile)
	config, err := store.Load()
	if err != nil {
		return nil, err
	}
	if _, err := os.Stat(filepath.Join(root, "config", configFile)); errors.Is(err, os.ErrNotExist) {
		config = defaults
		if proxy := strings.TrimSpace(os.Getenv("DEIMOS_TOR_PROXY")); proxy != "" {
			config.TorProxy = proxy
		}
	}
	return &Manager{store: store, hub: hub, config: config, name: name}, nil
}

func (m *Manager) Config() Config {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.config
}

func (m *Manager) UpdateConfig(config Config) (Config, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.running {
		return Config{}, errors.New("stop the crawler before changing its configuration")
	}
	updated, err := m.store.Save(config)
	if err != nil {
		return Config{}, err
	}
	m.config = updated
	m.publish("engine.config", m.name+" configuration saved", "success", map[string]any{"config": updated})
	return updated, nil
}

func (m *Manager) Start() error {
	m.mu.Lock()
	if m.running {
		m.mu.Unlock()
		return errors.New("crawler is already running")
	}
	config := m.config
	database, err := openDatabase(m.store.DatabasePath(config))
	if err != nil {
		m.mu.Unlock()
		return fmt.Errorf("open crawler database: %w", err)
	}
	client, err := buildHTTPClient(config)
	if err != nil {
		_ = database.close()
		m.mu.Unlock()
		return err
	}
	seeds, err := m.store.Seeds()
	if err != nil {
		_ = database.close()
		m.mu.Unlock()
		return err
	}
	for _, seed := range seeds {
		if err := database.addTask(seed.URL, 0, "seed", true); err != nil {
			_ = database.close()
			m.mu.Unlock()
			return err
		}
	}
	ctx, cancel := context.WithCancel(context.Background())
	m.database = database
	m.client = client
	m.cancel = cancel
	m.done = make(chan struct{})
	m.running = true
	m.started = time.Now().UTC()
	m.pages.Store(0)
	m.failures.Store(0)
	done := m.done
	m.mu.Unlock()

	go m.reseedLoop(ctx, database, 5*time.Minute)

	var workers sync.WaitGroup
	for id := 1; id <= config.ConcurrentCrawlers; id++ {
		workers.Add(1)
		go func(workerID int) {
			defer workers.Done()
			m.worker(ctx, workerID, config, database, client)
		}(id)
	}
	go func() {
		workers.Wait()
		_ = database.close()
		m.mu.Lock()
		m.running = false
		m.database = nil
		m.client = nil
		m.cancel = nil
		close(done)
		m.mu.Unlock()
		m.publish("engine.status", m.name+" stopped", "warning", nil)
	}()
	m.publish("engine.status", fmt.Sprintf("%s started with %d workers", m.name, config.ConcurrentCrawlers), "success", map[string]any{"config": config})
	return nil
}

// reseedLoop keeps an engine alive as a continuous crawler. Completed seed
// URLs are scheduled again periodically so changed pages and newly published
// links are discovered without restarting the service.
func (m *Manager) reseedLoop(ctx context.Context, database *crawlDatabase, interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			seeds, err := m.store.Seeds()
			if err != nil {
				m.publish("engine.error", m.name+" could not reload seeds: "+err.Error(), "warning", nil)
				continue
			}
			for _, seed := range seeds {
				_ = database.addTask(seed.URL, 0, "scheduled-seed", true)
			}
			m.publish("engine.queue", fmt.Sprintf("%s scheduled %d seeds for continuous discovery", m.name, len(seeds)), "info", map[string]any{"count": len(seeds)})
		}
	}
}

func (m *Manager) Stop() error {
	m.mu.RLock()
	if !m.running || m.cancel == nil {
		m.mu.RUnlock()
		return errors.New("crawler is not running")
	}
	cancel, done := m.cancel, m.done
	m.mu.RUnlock()
	cancel()
	select {
	case <-done:
		return nil
	case <-time.After(10 * time.Second):
		return errors.New("crawler stop timed out while requests were finishing")
	}
}

func (m *Manager) Status() Status {
	m.mu.RLock()
	running, started, database := m.running, m.started, m.database
	m.mu.RUnlock()
	status := Status{Running: running, PagesCrawled: m.pages.Load(), RequestErrors: m.failures.Load(), ActiveWorkers: int(m.workers.Load())}
	if !started.IsZero() {
		status.StartedAt = started.Format(time.RFC3339)
	}
	if database != nil {
		status.IndexedPages, status.PendingURLs, status.FailedURLs = database.counts()
	}
	return status
}

func (m *Manager) Seeds() ([]Seed, error) { return m.store.Seeds() }

func (m *Manager) AddSeed(seed Seed) ([]Seed, error) {
	seeds, err := m.store.AddSeed(seed)
	if err != nil {
		return nil, err
	}
	m.mu.RLock()
	database := m.database
	m.mu.RUnlock()
	if database != nil {
		_ = database.addTask(seed.URL, 0, "seed", true)
	}
	m.publish("engine.seed", m.name+" seed URL added", "success", map[string]any{"url": seed.URL})
	return seeds, nil
}

func (m *Manager) DeleteSeed(rawURL string) ([]Seed, error) {
	seeds, err := m.store.DeleteSeed(rawURL)
	if err == nil {
		m.publish("engine.seed", m.name+" seed URL removed", "warning", map[string]any{"url": rawURL})
	}
	return seeds, err
}

func (m *Manager) RetryFailed() (int64, error) {
	m.mu.RLock()
	database := m.database
	m.mu.RUnlock()
	if database == nil {
		config := m.Config()
		opened, err := openDatabase(m.store.DatabasePath(config))
		if err != nil {
			return 0, err
		}
		defer opened.close()
		database = opened
	}
	count, err := database.retryFailed()
	if err == nil {
		m.publish("engine.queue", fmt.Sprintf("%s requeued %d failed URLs", m.name, count), "success", map[string]any{"count": count})
	}
	return count, err
}

// QueueURL schedules a single investigation lead without making it a permanent seed.
// Running workers pick it up immediately; otherwise it remains queued for the next start.
func (m *Manager) QueueURL(rawURL, discoveredFrom string) error {
	parsed, err := url.Parse(strings.TrimSpace(rawURL))
	if err != nil {
		return fmt.Errorf("invalid URL: %w", err)
	}
	normalized, allowed := normalizeCrawlURL(parsed)
	if !allowed {
		return errors.New("URL is not an allowed crawl target")
	}
	m.mu.RLock()
	database := m.database
	m.mu.RUnlock()
	openedHere := false
	if database == nil {
		config := m.Config()
		database, err = openDatabase(m.store.DatabasePath(config))
		if err != nil {
			return err
		}
		openedHere = true
	}
	if openedHere {
		defer database.close()
	}
	if strings.TrimSpace(discoveredFrom) == "" {
		discoveredFrom = "workspace"
	}
	if err := database.addTask(normalized, 0, discoveredFrom, true); err != nil {
		return err
	}
	m.publish("workspace.queued", m.name+" queued workspace lead "+normalized, "success", map[string]any{"url": normalized})
	return nil
}

func (m *Manager) worker(ctx context.Context, workerID int, config Config, database *crawlDatabase, client *http.Client) {
	m.workers.Add(1)
	defer m.workers.Add(-1)
	m.publish("engine.worker", fmt.Sprintf("%s worker %02d ready", m.name, workerID), "info", nil)
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}
		m.claimMu.Lock()
		item, err := database.claimTask()
		m.claimMu.Unlock()
		if err != nil {
			m.failures.Add(1)
			m.publish("engine.error", fmt.Sprintf("%s worker %02d queue error: %v", m.name, workerID, err), "critical", nil)
			m.pause(ctx, time.Second)
			continue
		}
		if item == nil {
			m.pause(ctx, 2*time.Second)
			continue
		}
		parsedURL, parseErr := url.Parse(item.URL)
		normalizedURL, allowed := normalizeCrawlURL(parsedURL)
		if parseErr != nil || !allowed {
			database.complete(item.ID)
			m.publish("engine.skipped", fmt.Sprintf("%s skipped non-content route %s", m.name, item.URL), "info", map[string]any{"url": item.URL})
			continue
		}
		if normalizedURL != item.URL {
			database.complete(item.ID)
			_ = database.addTask(normalizedURL, item.Depth, item.URL, false)
			continue
		}
		m.publish("engine.fetch", fmt.Sprintf("%s worker %02d fetching %s", m.name, workerID, item.URL), "info", map[string]any{"url": item.URL, "depth": item.Depth})
		fetched, err := fetch(ctx, client, config, item.URL)
		if err != nil {
			database.fail(item.ID)
			m.failures.Add(1)
			m.publish("engine.error", fmt.Sprintf("%s fetch failed for %s: %v", m.name, item.URL, err), "warning", map[string]any{"url": item.URL})
			continue
		}
		parsed := parsePage(fetched.HTML, item.URL, item.Depth)
		parsed.StatusCode, parsed.ContentType, parsed.Server, parsed.PoweredBy, parsed.Headers, parsed.TLS = fetched.StatusCode, fetched.ContentType, fetched.Server, fetched.PoweredBy, fetched.Headers, fetched.TLS
		if item.Depth == 0 {
			parsed.StatusPages = probeStatusPages(ctx, client, config, item.URL)
		}
		if err := database.savePage(parsed); err != nil {
			database.fail(item.ID)
			m.failures.Add(1)
			m.publish("engine.error", fmt.Sprintf("%s index failed for %s: %v", m.name, item.URL, err), "critical", nil)
			continue
		}
		database.complete(item.ID)
		m.pages.Add(1)
		if item.Depth < config.MaxDepth {
			for _, link := range parsed.Links {
				if shouldFollow(item.URL, link, config.SameHostOnly) {
					_ = database.addTask(link, item.Depth+1, item.URL, false)
				}
			}
		}
		m.publish("engine.indexed", fmt.Sprintf("%s indexed %s", m.name, item.URL), "success", map[string]any{"url": item.URL, "title": parsed.Title, "depth": item.Depth})
		m.pause(ctx, time.Duration(config.DownloadDelay*float64(time.Second)))
	}
}

func (m *Manager) pause(ctx context.Context, duration time.Duration) {
	select {
	case <-ctx.Done():
	case <-time.After(duration):
	}
}

func (m *Manager) publish(eventType, message, level string, data map[string]any) {
	if data == nil {
		data = map[string]any{}
	}
	data["engine"] = m.name
	m.hub.Publish(events.Event{Type: eventType, Source: "go", Message: message, Level: level, Data: data})
}

package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strings"
	"sync"
	"time"
)

type Config struct {
	Crawler CrawlerConfig `json:"crawler"`
	Status  StatusConfig  `json:"status"`
}

type CrawlerConfig struct {
	MaxDepth           int     `json:"max_depth"`
	ConcurrentCrawlers int     `json:"concurrent_crawlers"`
	DownloadDelay      float64 `json:"download_delay"`
	UseTor             bool    `json:"use_tor"`
	TorProxy           string  `json:"tor_proxy"`
	DatabasePath       string  `json:"database_path"`
	SeedURLsPath       string  `json:"seed_urls_path"`
}

type StatusConfig struct {
	Running      bool   `json:"running"`
	LastStarted  string `json:"last_started"`
	PagesCrawled int    `json:"pages_crawled"`
}

type Crawler struct {
	Config    *Config
	Database  *Database
	TorClient *HTTPClient
	Semaphore chan struct{}
	Logs      []string
	LogsMutex sync.Mutex
	Running   bool
	Workers   int
}

var crawler *Crawler

func main() {
	config := loadConfig()

	crawler = &Crawler{
		Config:    config,
		Semaphore: make(chan struct{}, config.Crawler.ConcurrentCrawlers),
		Logs:      make([]string, 0),
		Running:   false,
		Workers:   config.Crawler.ConcurrentCrawlers,
	}

	crawler.TorClient = initializeTorClient(config.Crawler.TorProxy)

	db, err := initDatabase(config.Crawler.DatabasePath)
	if err != nil {
		log.Fatal("Failed to initialize database:", err)
	}
	crawler.Database = db
	defer db.Close()

	if err := loadSeedURLsToDatabase(config.Crawler.SeedURLsPath, db); err != nil {
		log.Printf("Error loading seed URLs: %v", err)
	} else {
		crawler.addLog("Seed URLs loaded into queue")
	}

	fmt.Println("\n╔════════════════════════════════════════════════════════════╗")
	fmt.Println("║              PHOBOS DARK WEB CRAWLER v2.0                  ║")
	fmt.Println("╚════════════════════════════════════════════════════════════╝")
	fmt.Printf("\n[DATABASE] %s\n", config.Crawler.DatabasePath)
	fmt.Printf("[TOR PROXY] %s\n", config.Crawler.TorProxy)
	fmt.Printf("[WORKERS] %d concurrent crawlers ready\n", crawler.Workers)
	fmt.Printf("[MAX DEPTH] %d levels\n", config.Crawler.MaxDepth)
	fmt.Println("\n[STATUS] Waiting for start command...")
	fmt.Println("────────────────────────────────────────────────────────────\n")

	monitorConfigChanges()
}

func loadConfig() *Config {
	// Retry up to 3 times in case of concurrent write
	var config Config
	var err error

	for i := 0; i < 3; i++ {
		file, readErr := os.ReadFile("config.json")
		if readErr != nil {
			if i == 2 {
				log.Fatal("Error reading config:", readErr)
			}
			time.Sleep(100 * time.Millisecond)
			continue
		}

		err = json.Unmarshal(file, &config)
		if err == nil {
			return &config
		}

		// If JSON parse failed, wait and retry
		time.Sleep(100 * time.Millisecond)
	}

	log.Fatal("Error parsing config after retries:", err)
	return nil
}

func saveConfig(config *Config) {
	data, _ := json.MarshalIndent(config, "", "    ")
	os.WriteFile("config.json", data, 0644)
}

func monitorConfigChanges() {
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()

	for range ticker.C {
		config := loadConfig()

		if config.Status.Running && !crawler.Running {
			crawler.addLog("✓ STARTING CRAWLER ENGINE")
			crawler.Running = true
			go startIntelligentCrawler()
		}

		if !config.Status.Running && crawler.Running {
			crawler.addLog("✗ STOPPING CRAWLER ENGINE")
			crawler.Running = false
		}
	}
}

func (c *Crawler) addLog(message string) {
	c.LogsMutex.Lock()
	defer c.LogsMutex.Unlock()

	timestamp := time.Now().Format("15:04:05")
	logEntry := fmt.Sprintf("[%s] %s", timestamp, message)
	c.Logs = append(c.Logs, logEntry)

	if len(c.Logs) > 1000 {
		c.Logs = c.Logs[len(c.Logs)-1000:]
	}

	fmt.Println(logEntry)
}

func startIntelligentCrawler() {
	crawler.addLog(fmt.Sprintf("► Launching %d worker goroutines...", crawler.Workers))

	// Start worker pool - each worker runs continuously
	for i := 0; i < crawler.Workers; i++ {
		go crawlerWorker(i + 1)
		time.Sleep(50 * time.Millisecond) // Stagger worker starts
	}

	crawler.addLog(fmt.Sprintf("✓ All %d workers active and hunting", crawler.Workers))

	// Monitor stats
	go statsMonitor()
}

func crawlerWorker(workerID int) {
	crawler.addLog(fmt.Sprintf("  Worker #%02d ready", workerID))

	for crawler.Running {
		// Get next task
		tasks := crawler.Database.GetPendingTasks(1)

		if len(tasks) == 0 {
			time.Sleep(3 * time.Second)
			continue
		}

		task := tasks[0]

		// Acquire semaphore
		crawler.Semaphore <- struct{}{}

		// Crawl the page
		crawlPage(task, workerID)

		// Release semaphore
		<-crawler.Semaphore

		// Polite delay
		time.Sleep(time.Duration(crawler.Config.Crawler.DownloadDelay * float64(time.Second)))
	}

	crawler.addLog(fmt.Sprintf("  Worker #%02d stopped", workerID))
}

func crawlPage(task CrawlTask, workerID int) {
	url := task.URL
	depth := task.Depth

	// Truncate URL for display
	displayURL := url
	if len(displayURL) > 65 {
		displayURL = displayURL[:65] + "..."
	}

	crawler.addLog(fmt.Sprintf("W%02d → [D:%d] Fetching: %s", workerID, depth, displayURL))

	// Fetch page
	html, err := crawler.TorClient.Fetch(url)
	if err != nil {
		crawler.addLog(fmt.Sprintf("W%02d ✗ Failed: %s", workerID, err.Error()[:50]))
		crawler.Database.MarkTaskFailed(task.ID)
		return
	}

	// Parse HTML
	parsed := parseHTML(html, url)

	// Save page
	pageID := crawler.Database.SavePage(parsed)

	if pageID > 0 {
		titleDisplay := parsed.Title
		if len(titleDisplay) > 50 {
			titleDisplay = titleDisplay[:50] + "..."
		}

		crawler.addLog(fmt.Sprintf("W%02d ✓ INDEXED [%d chars] %s", workerID, len(parsed.Content), titleDisplay))
		crawler.Database.MarkTaskCompleted(task.ID)

		// Update page count
		crawler.Config.Status.PagesCrawled++
		saveConfig(crawler.Config)

		// Add new links to queue
		if depth < crawler.Config.Crawler.MaxDepth {
			linksAdded := 0
			totalLinks := len(parsed.OutboundLinks)

			for _, link := range parsed.OutboundLinks {
				if isDarkWebURL(link) {
					crawler.Database.AddTask(link, depth+1, url)
					linksAdded++
				}
			}

			if linksAdded > 0 {
				crawler.addLog(fmt.Sprintf("W%02d   └─ Queued %d new .onion links (found %d total links)", workerID, linksAdded, totalLinks))
			} else if totalLinks > 0 {
				crawler.addLog(fmt.Sprintf("W%02d   └─ Found %d links but none were .onion URLs", workerID, totalLinks))
			} else {
				crawler.addLog(fmt.Sprintf("W%02d   └─ No links found on page", workerID))
			}
		}
	} else {
		crawler.addLog(fmt.Sprintf("W%02d ✗ Failed to save page", workerID))
		crawler.Database.MarkTaskFailed(task.ID)
	}
}

func statsMonitor() {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for range ticker.C {
		if !crawler.Running {
			return
		}

		indexed := crawler.Database.CountIndexedPages()
		queue := crawler.Database.GetQueueSize()

		crawler.addLog(fmt.Sprintf("═══ STATS: %d pages indexed | %d in queue | %d workers active ═══",
			indexed, queue, crawler.Workers))
	}
}

func isDarkWebURL(url string) bool {
	if len(url) == 0 {
		return false
	}
	return strings.Contains(url, ".onion") && (strings.HasPrefix(url, "http://") || strings.HasPrefix(url, "https://"))
}

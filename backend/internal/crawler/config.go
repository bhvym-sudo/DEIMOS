package crawler

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

type Config struct {
	MaxDepth           int     `json:"max_depth"`
	ConcurrentCrawlers int     `json:"concurrent_crawlers"`
	DownloadDelay      float64 `json:"download_delay"`
	UseTor             bool    `json:"use_tor"`
	TorProxy           string  `json:"tor_proxy"`
	RequestTimeout     int     `json:"request_timeout_seconds"`
	MaxBodyBytes       int64   `json:"max_body_bytes"`
	UserAgent          string  `json:"user_agent"`
	DatabasePath       string  `json:"database_path"`
	SameHostOnly       bool    `json:"same_host_only"`
}

type Seed struct {
	URL       string `json:"url"`
	WebType   string `json:"web_type"`
	AddedBy   string `json:"added_by,omitempty"`
	Remarks   string `json:"remarks,omitempty"`
	Timestamp string `json:"timestamp"`
}

type ConfigStore struct {
	mu         sync.RWMutex
	root       string
	configPath string
	seedsPath  string
}

func NewConfigStore(root string) *ConfigStore {
	return NewConfigStoreForEngine(root, "crawler.json", "crawler-seeds.json")
}

func NewConfigStoreForEngine(root, configFile, seedsFile string) *ConfigStore {
	return &ConfigStore{
		root:       root,
		configPath: filepath.Join(root, "config", configFile),
		seedsPath:  filepath.Join(root, "config", seedsFile),
	}
}

func DefaultConfig() Config {
	return Config{
		MaxDepth:           3,
		ConcurrentCrawlers: 10,
		DownloadDelay:      1,
		UseTor:             true,
		TorProxy:           "127.0.0.1:9050",
		RequestTimeout:     60,
		MaxBodyBytes:       5 * 1024 * 1024,
		UserAgent:          "DEIMOS-Collector/0.2 (+authorized-security-research)",
		DatabasePath:       "phobos/databases/phobos_index.db",
		SameHostOnly:       true,
	}
}

func DefaultConfigFor(databasePath, userAgent string) Config {
	config := DefaultConfig()
	config.DatabasePath = databasePath
	config.UserAgent = userAgent
	return config
}

func (s *ConfigStore) Load() (Config, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	config := DefaultConfig()
	payload, err := os.ReadFile(s.configPath)
	if errors.Is(err, os.ErrNotExist) {
		return config, nil
	}
	if err != nil {
		return Config{}, err
	}
	if err := json.Unmarshal(payload, &config); err != nil {
		return Config{}, fmt.Errorf("decode crawler config: %w", err)
	}
	if value := strings.TrimSpace(os.Getenv("DEIMOS_TOR_PROXY")); value != "" {
		config.TorProxy = value
	}
	if value := strings.TrimSpace(os.Getenv("DEIMOS_DATABASE_PATH")); value != "" {
		config.DatabasePath = value
	}
	return normalizeConfig(config)
}

func (s *ConfigStore) Save(config Config) (Config, error) {
	normalized, err := normalizeConfig(config)
	if err != nil {
		return Config{}, err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if err := writeJSONAtomic(s.configPath, normalized); err != nil {
		return Config{}, err
	}
	return normalized, nil
}

func (s *ConfigStore) Seeds() ([]Seed, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.readSeeds()
}

func (s *ConfigStore) AddSeed(seed Seed) ([]Seed, error) {
	seed.URL = strings.TrimSpace(seed.URL)
	parsed, err := url.Parse(seed.URL)
	if err != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.Hostname() == "" {
		return nil, errors.New("seed must be a valid http or https URL")
	}
	if seed.WebType == "" {
		if strings.HasSuffix(strings.ToLower(parsed.Hostname()), ".onion") {
			seed.WebType = "dark_web"
		} else {
			seed.WebType = "surface_web"
		}
	}
	if seed.Timestamp == "" {
		seed.Timestamp = time.Now().UTC().Format(time.RFC3339)
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	seeds, err := s.readSeeds()
	if err != nil {
		return nil, err
	}
	for _, existing := range seeds {
		if strings.EqualFold(existing.URL, seed.URL) {
			return nil, errors.New("seed URL already exists")
		}
	}
	seeds = append(seeds, seed)
	if err := writeJSONAtomic(s.seedsPath, seeds); err != nil {
		return nil, err
	}
	return seeds, nil
}

func (s *ConfigStore) DeleteSeed(rawURL string) ([]Seed, error) {
	rawURL = strings.TrimSpace(rawURL)
	s.mu.Lock()
	defer s.mu.Unlock()
	seeds, err := s.readSeeds()
	if err != nil {
		return nil, err
	}
	filtered := make([]Seed, 0, len(seeds))
	found := false
	for _, seed := range seeds {
		if seed.URL == rawURL {
			found = true
			continue
		}
		filtered = append(filtered, seed)
	}
	if !found {
		return nil, errors.New("seed URL not found")
	}
	if err := writeJSONAtomic(s.seedsPath, filtered); err != nil {
		return nil, err
	}
	return filtered, nil
}

func (s *ConfigStore) DatabasePath(config Config) string {
	if filepath.IsAbs(config.DatabasePath) {
		return config.DatabasePath
	}
	return filepath.Join(s.root, filepath.FromSlash(config.DatabasePath))
}

func (s *ConfigStore) readSeeds() ([]Seed, error) {
	payload, err := os.ReadFile(s.seedsPath)
	if errors.Is(err, os.ErrNotExist) {
		return []Seed{}, nil
	}
	if err != nil {
		return nil, err
	}
	var seeds []Seed
	if err := json.Unmarshal(payload, &seeds); err != nil {
		return nil, fmt.Errorf("decode seeds: %w", err)
	}
	return seeds, nil
}

func normalizeConfig(config Config) (Config, error) {
	if config.MaxDepth < 0 || config.MaxDepth > 12 {
		return Config{}, errors.New("max_depth must be between 0 and 12")
	}
	if config.ConcurrentCrawlers < 1 || config.ConcurrentCrawlers > 50 {
		return Config{}, errors.New("concurrent_crawlers must be between 1 and 50")
	}
	if config.DownloadDelay < 0 || config.DownloadDelay > 60 {
		return Config{}, errors.New("download_delay must be between 0 and 60 seconds")
	}
	if config.RequestTimeout < 5 || config.RequestTimeout > 300 {
		return Config{}, errors.New("request_timeout_seconds must be between 5 and 300")
	}
	if config.MaxBodyBytes < 1024 || config.MaxBodyBytes > 25*1024*1024 {
		return Config{}, errors.New("max_body_bytes must be between 1 KB and 25 MB")
	}
	if strings.TrimSpace(config.DatabasePath) == "" {
		return Config{}, errors.New("database_path is required")
	}
	if config.UseTor && strings.TrimSpace(config.TorProxy) == "" {
		return Config{}, errors.New("tor_proxy is required when Tor routing is enabled")
	}
	if strings.TrimSpace(config.UserAgent) == "" {
		config.UserAgent = DefaultConfig().UserAgent
	}
	return config, nil
}

func writeJSONAtomic(path string, value any) error {
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return err
	}
	payload, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	temp := path + ".tmp"
	if err := os.WriteFile(temp, append(payload, '\n'), 0644); err != nil {
		return err
	}
	return os.Rename(temp, path)
}

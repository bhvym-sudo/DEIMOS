package server

import (
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"deimos/internal/crawler"
	"deimos/internal/events"
	"deimos/internal/store"
	"github.com/gorilla/websocket"
)

type engine struct {
	slug    string
	name    string
	manager *crawler.Manager
	store   *store.Store
}

type Server struct {
	root         string
	hub          *events.Hub
	crawler      *engine
	phobosSearch *engine
}

func New(root string) (*Server, error) {
	hub := events.New()
	crawlerManager, err := crawler.NewEngineManager(root, hub, "Crawler", "crawler.json", "crawler-seeds.json", crawler.DefaultConfigFor("phobos/databases/crawler.db", "DEIMOS-Crawler/0.3 (+authorized-security-research)"))
	if err != nil {
		return nil, err
	}
	searchManager, err := crawler.NewEngineManager(root, hub, "PHOBOS Search", "phobos-search.json", "phobos-search-seeds.json", crawler.DefaultConfigFor("phobos/databases/phobos_search.db", "PHOBOS-Search/0.3 (+authorized-security-research)"))
	if err != nil {
		return nil, err
	}
	crawlerDB := filepath.Join(root, "phobos", "databases", "crawler.db")
	searchDB := filepath.Join(root, "phobos", "databases", "phobos_search.db")
	crawlerStore, err := store.Open(crawlerDB, crawlerDB)
	if err != nil {
		return nil, err
	}
	searchStore, err := store.Open(searchDB, searchDB)
	if err != nil {
		crawlerStore.Close()
		return nil, err
	}
	return &Server{
		root: root, hub: hub,
		crawler:      &engine{slug: "crawler", name: "Crawler", manager: crawlerManager, store: crawlerStore},
		phobosSearch: &engine{slug: "phobos-search", name: "PHOBOS Search", manager: searchManager, store: searchStore},
	}, nil
}

func (s *Server) Close() { s.crawler.store.Close(); s.phobosSearch.store.Close() }

func (s *Server) StartEngines() {
	if err := s.phobosSearch.manager.Start(); err != nil {
		s.hub.Publish(events.Event{Type: "engine.error", Source: "go", Message: "PHOBOS Search auto-start failed: " + err.Error(), Level: "critical"})
	}
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/health", s.health)
	mux.HandleFunc("GET /api/tor/health", s.torHealth)
	s.registerEngine(mux, s.crawler, false)
	s.registerEngine(mux, s.phobosSearch, true)
	// Compatibility routes for clients built before the engine split.
	mux.HandleFunc("GET /api/stats", s.engineStats(s.phobosSearch))
	mux.HandleFunc("GET /api/search", s.search)
	mux.HandleFunc("GET /ws", s.websocket)
	return s.localCORS(mux)
}

func (s *Server) registerEngine(mux *http.ServeMux, value *engine, searchable bool) {
	prefix := "/api/" + value.slug
	mux.HandleFunc("GET "+prefix+"/stats", s.engineStats(value))
	mux.HandleFunc("GET "+prefix+"/status", func(w http.ResponseWriter, _ *http.Request) { writeJSON(w, http.StatusOK, value.manager.Status()) })
	mux.HandleFunc("GET "+prefix+"/config", func(w http.ResponseWriter, _ *http.Request) { writeJSON(w, http.StatusOK, value.manager.Config()) })
	mux.HandleFunc("PUT "+prefix+"/config", s.updateConfig(value))
	mux.HandleFunc("GET "+prefix+"/seeds", s.seeds(value))
	mux.HandleFunc("POST "+prefix+"/seeds", s.addSeed(value))
	mux.HandleFunc("DELETE "+prefix+"/seeds", s.deleteSeed(value))
	mux.HandleFunc("POST "+prefix+"/start", s.start(value))
	mux.HandleFunc("POST "+prefix+"/stop", s.stop(value))
	mux.HandleFunc("POST "+prefix+"/retry-failed", s.retryFailed(value))
	mux.HandleFunc("GET "+prefix+"/pages", s.pages(value))
	mux.HandleFunc("GET "+prefix+"/pages/{id}", s.page(value))
	if searchable {
		mux.HandleFunc("GET "+prefix+"/search", s.search)
	}
}

func (s *Server) pages(value *engine) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
		offset, _ := strconv.Atoi(r.URL.Query().Get("offset"))
		records, total, err := value.store.Pages(r.URL.Query().Get("q"), limit, offset)
		if err != nil {
			writeError(w, 500, err)
			return
		}
		writeJSON(w, 200, map[string]any{"pages": records, "count": len(records), "total": total})
	}
}
func (s *Server) page(value *engine) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id, err := strconv.Atoi(r.PathValue("id"))
		if err != nil {
			writeError(w, 400, fmt.Errorf("invalid page id"))
			return
		}
		record, err := value.store.Page(id)
		if err != nil {
			writeError(w, 404, err)
			return
		}
		writeJSON(w, 200, record)
	}
}

func (s *Server) StartHeartbeat() {
	go func() {
		ticker := time.NewTicker(10 * time.Second)
		defer ticker.Stop()
		for range ticker.C {
			crawlerStatus := s.crawler.manager.Status()
			searchStatus := s.phobosSearch.manager.Status()
			s.hub.Publish(events.Event{Type: "heartbeat", Source: "go", Message: "DEIMOS crawler engines operational", Level: "info", Data: map[string]any{
				"crawler":       s.crawler.store.Stats(crawlerStatus.Running, s.crawler.manager.Config().UseTor),
				"phobos_search": s.phobosSearch.store.Stats(searchStatus.Running, s.phobosSearch.manager.Config().UseTor),
			}})
		}
	}()
}

func (s *Server) health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "service": "deimos-go-gateway", "crawler": s.crawler.manager.Status(), "phobos_search": s.phobosSearch.manager.Status()})
}

func (s *Server) torHealth(w http.ResponseWriter, _ *http.Request) {
	address := strings.TrimSpace(s.phobosSearch.manager.Config().TorProxy)
	if address == "" {
		writeJSON(w, http.StatusOK, map[string]any{"status": "offline", "message": "Tor proxy is not configured"})
		return
	}
	connection, err := net.DialTimeout("tcp", address, 2*time.Second)
	if err != nil {
		writeJSON(w, http.StatusOK, map[string]any{"status": "offline", "address": address, "message": err.Error()})
		return
	}
	_ = connection.Close()
	writeJSON(w, http.StatusOK, map[string]any{"status": "online", "address": address})
}

func (s *Server) engineStats(value *engine) http.HandlerFunc {
	return func(w http.ResponseWriter, _ *http.Request) {
		status, config := value.manager.Status(), value.manager.Config()
		writeJSON(w, http.StatusOK, value.store.Stats(status.Running, config.UseTor))
	}
}

func (s *Server) search(w http.ResponseWriter, r *http.Request) {
	started := time.Now()
	query := strings.TrimSpace(r.URL.Query().Get("q"))
	displayQuery := query
	if len(displayQuery) > 80 {
		displayQuery = displayQuery[:80] + "…"
	}
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	s.hub.Publish(events.Event{Type: "search.started", Source: "go", Message: fmt.Sprintf("PHOBOS Search querying index for %q", displayQuery), Level: "info", Data: map[string]any{"engine": "PHOBOS Search"}})
	results, err := s.phobosSearch.store.Search(query, limit)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	s.hub.Publish(events.Event{Type: "search.completed", Source: "go", Message: fmt.Sprintf("PHOBOS Search returned %d results for %q", len(results), displayQuery), Level: "success", Data: map[string]any{"engine": "PHOBOS Search", "duration_ms": time.Since(started).Milliseconds()}})
	writeJSON(w, http.StatusOK, map[string]any{"results": results, "count": len(results)})
}

func (s *Server) seeds(value *engine) http.HandlerFunc {
	return func(w http.ResponseWriter, _ *http.Request) {
		items, err := value.manager.Seeds()
		if err != nil {
			writeError(w, 500, err)
			return
		}
		writeJSON(w, 200, map[string]any{"seeds": items, "count": len(items)})
	}
}
func (s *Server) addSeed(value *engine) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var seed crawler.Seed
		if err := decodeJSON(r, &seed); err != nil {
			writeError(w, 400, err)
			return
		}
		items, err := value.manager.AddSeed(seed)
		if err != nil {
			writeError(w, 400, err)
			return
		}
		writeJSON(w, 201, map[string]any{"message": value.name + " seed URL added", "seeds": items})
	}
}
func (s *Server) deleteSeed(value *engine) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var request struct {
			URL string `json:"url"`
		}
		if err := decodeJSON(r, &request); err != nil {
			writeError(w, 400, err)
			return
		}
		items, err := value.manager.DeleteSeed(request.URL)
		if err != nil {
			writeError(w, 404, err)
			return
		}
		writeJSON(w, 200, map[string]any{"message": value.name + " seed URL removed", "seeds": items})
	}
}
func (s *Server) updateConfig(value *engine) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var config crawler.Config
		if err := decodeJSON(r, &config); err != nil {
			writeError(w, 400, err)
			return
		}
		updated, err := value.manager.UpdateConfig(config)
		if err != nil {
			writeError(w, 409, err)
			return
		}
		writeJSON(w, 200, map[string]any{"message": value.name + " configuration saved", "config": updated})
	}
}
func (s *Server) start(value *engine) http.HandlerFunc {
	return func(w http.ResponseWriter, _ *http.Request) {
		if err := value.manager.Start(); err != nil {
			writeError(w, 409, err)
			return
		}
		writeJSON(w, 202, map[string]any{"message": value.name + " started", "status": value.manager.Status()})
	}
}
func (s *Server) stop(value *engine) http.HandlerFunc {
	return func(w http.ResponseWriter, _ *http.Request) {
		if err := value.manager.Stop(); err != nil {
			writeError(w, 409, err)
			return
		}
		writeJSON(w, 200, map[string]any{"message": value.name + " stopped", "status": value.manager.Status()})
	}
}
func (s *Server) retryFailed(value *engine) http.HandlerFunc {
	return func(w http.ResponseWriter, _ *http.Request) {
		count, err := value.manager.RetryFailed()
		if err != nil {
			writeError(w, 500, err)
			return
		}
		writeJSON(w, 200, map[string]any{"message": fmt.Sprintf("%s requeued %d failed URLs", value.name, count), "count": count})
	}
}

func allowedOrigin(origin string) bool {
	if origin == "" { return true }
	configured := os.Getenv("DEIMOS_ALLOWED_ORIGINS")
	if configured == "" { configured = "http://localhost:3000,http://127.0.0.1:3000,http://10.12.13.8:3000" }
	for _, allowed := range strings.Split(configured, ",") { if strings.TrimSpace(allowed) == origin { return true } }
	return false
}

var upgrader = websocket.Upgrader{ReadBufferSize: 1024, WriteBufferSize: 1024, CheckOrigin: func(r *http.Request) bool { return allowedOrigin(r.Header.Get("Origin")) }}

func (s *Server) websocket(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		return
	}
	s.hub.Add(conn)
	s.hub.Publish(events.Event{Type: "connection", Source: "go", Message: "Frontend connected to DEIMOS Go gateway", Level: "success"})
	for {
		if _, _, err := conn.ReadMessage(); err != nil {
			s.hub.Remove(conn)
			return
		}
	}
}
func (s *Server) localCORS(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		if origin != "" && !allowedOrigin(origin) { http.Error(w, "origin not allowed", http.StatusForbidden); return }
		if origin != "" {
			w.Header().Set("Access-Control-Allow-Origin", origin)
			w.Header().Add("Vary", "Origin")
		}
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization, Accept, X-Requested-With")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Max-Age", "600")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}
func decodeJSON(r *http.Request, target any) error {
	decoder := json.NewDecoder(io.LimitReader(r.Body, 1024*1024))
	decoder.DisallowUnknownFields()
	return decoder.Decode(target)
}
func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
func writeError(w http.ResponseWriter, status int, err error) {
	writeJSON(w, status, map[string]string{"error": err.Error()})
}
func ListenAddress() string {
	if value := os.Getenv("DEIMOS_GO_ADDR"); value != "" {
		return value
	}
	return "127.0.0.1:8787"
}
func RootFromWorkingDirectory() (string, error) {
	if value := os.Getenv("DEIMOS_ROOT"); value != "" {
		return filepath.Abs(value)
	}
	current, err := os.Getwd()
	if err != nil {
		return "", err
	}
	for candidate := current; ; candidate = filepath.Dir(candidate) {
		if info, statErr := os.Stat(filepath.Join(candidate, "config")); statErr == nil && info.IsDir() {
			return candidate, nil
		}
		parent := filepath.Dir(candidate)
		if parent == candidate {
			break
		}
	}
	return "", fmt.Errorf("could not locate DEIMOS root from %s", current)
}
func Banner(address string) string {
	return fmt.Sprintf("DEIMOS Go gateway listening on http://%s", address)
}

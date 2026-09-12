package events

import (
	"encoding/json"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

type Event struct {
	Type      string         `json:"type"`
	Source    string         `json:"source"`
	Message   string         `json:"message"`
	Timestamp time.Time      `json:"timestamp"`
	Level     string         `json:"level,omitempty"`
	Data      map[string]any `json:"data,omitempty"`
}

type Hub struct {
	mu      sync.RWMutex
	writeMu sync.Mutex
	clients map[*websocket.Conn]struct{}
}

func New() *Hub { return &Hub{clients: make(map[*websocket.Conn]struct{})} }

func (h *Hub) Add(conn *websocket.Conn) {
	h.mu.Lock()
	h.clients[conn] = struct{}{}
	h.mu.Unlock()
}

func (h *Hub) Remove(conn *websocket.Conn) {
	h.mu.Lock()
	delete(h.clients, conn)
	h.mu.Unlock()
	_ = conn.Close()
}

func (h *Hub) Publish(event Event) {
	h.writeMu.Lock()
	defer h.writeMu.Unlock()
	if event.Timestamp.IsZero() {
		event.Timestamp = time.Now()
	}
	payload, _ := json.Marshal(event)
	h.mu.RLock()
	clients := make([]*websocket.Conn, 0, len(h.clients))
	for client := range h.clients {
		clients = append(clients, client)
	}
	h.mu.RUnlock()
	for _, client := range clients {
		_ = client.SetWriteDeadline(time.Now().Add(3 * time.Second))
		if err := client.WriteMessage(websocket.TextMessage, payload); err != nil {
			h.Remove(client)
		}
	}
}

package main

import (
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"time"

	"golang.org/x/net/proxy"
)

type HTTPClient struct {
	client *http.Client
}

func initializeTorClient(torProxy string) *HTTPClient {
	dialer, err := proxy.SOCKS5("tcp", torProxy, nil, proxy.Direct)
	if err != nil {
		fmt.Println("[ERROR] Failed to create Tor SOCKS5 dialer:", err)
		return &HTTPClient{
			client: &http.Client{Timeout: 30 * time.Second},
		}
	}

	transport := &http.Transport{
		DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
			return dialer.Dial(network, addr)
		},
		MaxIdleConns:        100,
		MaxIdleConnsPerHost: 10,
		IdleConnTimeout:     90 * time.Second,
	}

	return &HTTPClient{
		client: &http.Client{
			Transport: transport,
			Timeout:   60 * time.Second,
		},
	}
}

func (c *HTTPClient) Fetch(url string) (string, error) {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return "", err
	}

	req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; rv:91.0) Gecko/20100101 Firefox/91.0")

	resp, err := c.client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return "", fmt.Errorf("HTTP %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	return string(body), nil
}

package crawler

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"

	"golang.org/x/net/html"
	"golang.org/x/net/proxy"
)

func buildHTTPClient(config Config) (*http.Client, error) {
	transport := &http.Transport{MaxIdleConns: config.ConcurrentCrawlers * 2, MaxIdleConnsPerHost: config.ConcurrentCrawlers, IdleConnTimeout: 60 * time.Second}
	if config.UseTor {
		dialer, err := proxy.SOCKS5("tcp", config.TorProxy, nil, proxy.Direct)
		if err != nil {
			return nil, fmt.Errorf("configure Tor SOCKS5 proxy: %w", err)
		}
		transport.DialContext = func(ctx context.Context, network, address string) (net.Conn, error) {
			return dialer.Dial(network, address)
		}
	}
	client := &http.Client{Transport: transport, Timeout: time.Duration(config.RequestTimeout) * time.Second}
	client.CheckRedirect = func(_ *http.Request, via []*http.Request) error {
		if len(via) >= 5 {
			return errors.New("redirect limit exceeded")
		}
		return nil
	}
	return client, nil
}

func fetch(ctx context.Context, client *http.Client, config Config, rawURL string) (string, error) {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, rawURL, nil)
	if err != nil {
		return "", err
	}
	request.Header.Set("User-Agent", config.UserAgent)
	request.Header.Set("Accept", "text/html,application/xhtml+xml")
	response, err := client.Do(request)
	if err != nil {
		return "", err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return "", fmt.Errorf("HTTP %d", response.StatusCode)
	}
	contentType := strings.ToLower(response.Header.Get("Content-Type"))
	if contentType != "" && !strings.Contains(contentType, "text/html") && !strings.Contains(contentType, "application/xhtml") {
		return "", fmt.Errorf("unsupported content type %s", contentType)
	}
	limited := io.LimitReader(response.Body, config.MaxBodyBytes+1)
	payload, err := io.ReadAll(limited)
	if err != nil {
		return "", err
	}
	if int64(len(payload)) > config.MaxBodyBytes {
		return "", errors.New("response exceeded configured size limit")
	}
	return string(payload), nil
}

func parsePage(htmlContent, rawURL string, depth int) page {
	document, err := html.Parse(strings.NewReader(htmlContent))
	if err != nil {
		return page{URL: rawURL, HTML: htmlContent, Depth: depth}
	}
	base, _ := url.Parse(rawURL)
	seen := map[string]bool{}
	links := make([]string, 0)
	var title string
	var content strings.Builder
	var visit func(*html.Node)
	visit = func(node *html.Node) {
		if node.Type == html.ElementNode {
			if node.Data == "script" || node.Data == "style" || node.Data == "noscript" {
				return
			}
			if node.Data == "title" && node.FirstChild != nil {
				title = strings.TrimSpace(node.FirstChild.Data)
			}
			if node.Data == "a" {
				for _, attribute := range node.Attr {
					if attribute.Key != "href" {
						continue
					}
					reference, err := url.Parse(attribute.Val)
					if err != nil {
						continue
					}
					resolved := base.ResolveReference(reference)
					resolved.Fragment = ""
					if (resolved.Scheme == "http" || resolved.Scheme == "https") && resolved.Hostname() != "" && !seen[resolved.String()] {
						seen[resolved.String()] = true
						links = append(links, resolved.String())
					}
				}
			}
		}
		if node.Type == html.TextNode {
			value := strings.TrimSpace(node.Data)
			if value != "" {
				content.WriteString(value)
				content.WriteByte(' ')
			}
		}
		for child := node.FirstChild; child != nil; child = child.NextSibling {
			visit(child)
		}
	}
	visit(document)
	clean := strings.Join(strings.Fields(content.String()), " ")
	return page{URL: rawURL, Title: title, Content: clean, HTML: htmlContent, Domain: base.Hostname(), Depth: depth, Links: links}
}

func shouldFollow(parent, candidate string, sameHostOnly bool) bool {
	parentURL, parentErr := url.Parse(parent)
	candidateURL, candidateErr := url.Parse(candidate)
	if parentErr != nil || candidateErr != nil || candidateURL.Hostname() == "" {
		return false
	}
	if sameHostOnly {
		return strings.EqualFold(parentURL.Hostname(), candidateURL.Hostname())
	}
	return strings.HasSuffix(strings.ToLower(candidateURL.Hostname()), ".onion")
}

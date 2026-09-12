package crawler

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
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

type tlsMetadata struct {
	Subject     string   `json:"subject"`
	Issuer      string   `json:"issuer"`
	Serial      string   `json:"serial"`
	NotBefore   string   `json:"not_before"`
	NotAfter    string   `json:"not_after"`
	DNSNames    []string `json:"dns_names"`
	Fingerprint string   `json:"fingerprint_sha256"`
}

type fetchResult struct {
	HTML        string
	StatusCode  int
	ContentType string
	Server      string
	PoweredBy   string
	Headers     map[string]string
	TLS         *tlsMetadata
}

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

func fetch(ctx context.Context, client *http.Client, config Config, rawURL string) (fetchResult, error) {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, rawURL, nil)
	if err != nil {
		return fetchResult{}, err
	}
	request.Header.Set("User-Agent", config.UserAgent)
	request.Header.Set("Accept", "text/html,application/xhtml+xml")
	response, err := client.Do(request)
	if err != nil {
		return fetchResult{}, err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return fetchResult{}, fmt.Errorf("HTTP %d", response.StatusCode)
	}
	contentType := strings.ToLower(response.Header.Get("Content-Type"))
	if contentType != "" && !strings.Contains(contentType, "text/html") && !strings.Contains(contentType, "application/xhtml") {
		return fetchResult{}, fmt.Errorf("unsupported content type %s", contentType)
	}
	limited := io.LimitReader(response.Body, config.MaxBodyBytes+1)
	payload, err := io.ReadAll(limited)
	if err != nil {
		return fetchResult{}, err
	}
	if int64(len(payload)) > config.MaxBodyBytes {
		return fetchResult{}, errors.New("response exceeded configured size limit")
	}
	headers := map[string]string{}
	for _, name := range []string{"Server", "X-Powered-By", "Via", "X-AspNet-Version", "X-Generator"} {
		if value := response.Header.Get(name); value != "" {
			headers[name] = value
		}
	}
	result := fetchResult{HTML: string(payload), StatusCode: response.StatusCode, ContentType: contentType, Server: response.Header.Get("Server"), PoweredBy: response.Header.Get("X-Powered-By"), Headers: headers}
	if response.TLS != nil && len(response.TLS.PeerCertificates) > 0 {
		certificate := response.TLS.PeerCertificates[0]
		fingerprint := sha256.Sum256(certificate.Raw)
		result.TLS = &tlsMetadata{Subject: certificate.Subject.String(), Issuer: certificate.Issuer.String(), Serial: certificate.SerialNumber.String(), NotBefore: certificate.NotBefore.UTC().Format(time.RFC3339), NotAfter: certificate.NotAfter.UTC().Format(time.RFC3339), DNSNames: certificate.DNSNames, Fingerprint: hex.EncodeToString(fingerprint[:])}
	}
	return result, nil
}

func probeStatusPages(ctx context.Context, client *http.Client, config Config, rawURL string) []map[string]any {
	base, err := url.Parse(rawURL)
	if err != nil || base.Hostname() == "" {
		return nil
	}
	results := make([]map[string]any, 0)
	for _, path := range []string{"/server-status", "/nginx_status", "/.well-known/security.txt"} {
		candidate := *base
		candidate.Path, candidate.RawQuery, candidate.Fragment = path, "", ""
		request, err := http.NewRequestWithContext(ctx, http.MethodHead, candidate.String(), nil)
		if err != nil {
			continue
		}
		request.Header.Set("User-Agent", config.UserAgent)
		response, err := client.Do(request)
		if err != nil {
			continue
		}
		_ = response.Body.Close()
		if response.StatusCode == http.StatusOK || response.StatusCode == http.StatusUnauthorized || response.StatusCode == http.StatusForbidden {
			results = append(results, map[string]any{"url": candidate.String(), "status_code": response.StatusCode, "server": response.Header.Get("Server")})
		}
	}
	return results
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

package main

import (
	"encoding/json"
	"net/url"
	"os"
	"regexp"
	"strings"

	"golang.org/x/net/html"
)

type ParsedPage struct {
	URL           string
	Title         string
	Content       string
	HTMLContent   string
	Domain        string
	ContentLength int
	OutboundLinks []string
}

func parseHTML(htmlContent string, baseURL string) PageData {
	doc, err := html.Parse(strings.NewReader(htmlContent))
	if err != nil {
		return PageData{URL: baseURL, HTMLContent: htmlContent}
	}

	var title string
	var textContent strings.Builder
	var links []string
	seenURLs := make(map[string]bool)

	var traverse func(*html.Node)
	traverse = func(n *html.Node) {
		if n.Type == html.ElementNode {
			switch n.Data {
			case "title":
				if n.FirstChild != nil {
					title = n.FirstChild.Data
				}
			case "a":
				for _, attr := range n.Attr {
					if attr.Key == "href" {
						href := attr.Val
						resolvedURL := resolveURL(baseURL, href)

						if resolvedURL != "" && !seenURLs[resolvedURL] {
							// Only add .onion links
							if strings.Contains(resolvedURL, ".onion") {
								// Filter out non-content URLs
								if !strings.Contains(resolvedURL, "#") &&
									!strings.Contains(resolvedURL, "javascript:") &&
									!strings.HasSuffix(resolvedURL, ".jpg") &&
									!strings.HasSuffix(resolvedURL, ".png") &&
									!strings.HasSuffix(resolvedURL, ".gif") &&
									!strings.HasSuffix(resolvedURL, ".css") &&
									!strings.HasSuffix(resolvedURL, ".js") &&
									!strings.HasSuffix(resolvedURL, ".pdf") {

									links = append(links, resolvedURL)
									seenURLs[resolvedURL] = true
								}
							}
						}
					}
				}
			case "script", "style", "noscript":
				return
			}
		}

		if n.Type == html.TextNode {
			text := strings.TrimSpace(n.Data)
			if len(text) > 0 {
				textContent.WriteString(text)
				textContent.WriteString(" ")
			}
		}

		for c := n.FirstChild; c != nil; c = c.NextSibling {
			traverse(c)
		}
	}

	traverse(doc)

	content := cleanText(textContent.String())
	domain := extractDomain(baseURL)

	return PageData{
		URL:           baseURL,
		Title:         strings.TrimSpace(title),
		Content:       content,
		HTMLContent:   htmlContent,
		Domain:        domain,
		ContentLength: len(content),
		OutboundLinks: links,
	}
}

func cleanText(text string) string {
	text = regexp.MustCompile(`\s+`).ReplaceAllString(text, " ")
	text = strings.TrimSpace(text)
	return text
}

func extractDomain(urlStr string) string {
	re := regexp.MustCompile(`https?://([^/]+)`)
	matches := re.FindStringSubmatch(urlStr)
	if len(matches) > 1 {
		return matches[1]
	}
	return ""
}

func resolveURL(baseURL, href string) string {
	base, err := url.Parse(baseURL)
	if err != nil {
		return ""
	}

	ref, err := url.Parse(href)
	if err != nil {
		return ""
	}

	resolved := base.ResolveReference(ref)
	return resolved.String()
}

func loadSeedURLsToDatabase(seedPath string, db *Database) error {
	data, err := os.ReadFile(seedPath)
	if err != nil {
		return err
	}

	var seeds struct {
		DarkWeb []struct {
			URL       string `json:"url"`
			AddedBy   string `json:"added_by"`
			Remarks   string `json:"remarks"`
			Timestamp string `json:"timestamp"`
		} `json:"dark_web"`
	}

	if err := json.Unmarshal(data, &seeds); err != nil {
		return err
	}

	for _, seed := range seeds.DarkWeb {
		if strings.Contains(seed.URL, ".onion") {
			db.AddTask(seed.URL, 0, "seed")
		}
	}

	return nil
}

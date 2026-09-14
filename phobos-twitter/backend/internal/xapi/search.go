package xapi

import (
	"context"
	"fmt"
	"net/url"
	"strings"
	"time"

	"trex/backend/internal/model"
)

type SearchProgress func(message string, progress int, post *model.Post)

// SearchTimeline replays the authenticated operation captured from the user's
// own X session. Docker therefore does not need to launch Electron or Edge.
func (c *Client) SearchTimeline(ctx context.Context, query, resultMode string, maxPosts, delaySeconds int, progress SearchProgress) ([]model.Post, error) {
	query = strings.TrimSpace(query)
	if query == "" {
		return nil, fmt.Errorf("search query is empty")
	}
	operation, ok := c.session.Operation("SearchTimeline")
	if !ok || operation.QueryID == "" {
		return nil, fmt.Errorf("SearchTimeline session metadata is missing; refresh the PHOBOS-Tweeter session")
	}
	if maxPosts <= 0 {
		maxPosts = 100
	}
	if delaySeconds <= 0 {
		delaySeconds = 3
	}
	product := "Latest"
	if strings.EqualFold(resultMode, "top") {
		product = "Top"
	}
	variables := cloneAnyMap(operation.Variables)
	variables["rawQuery"] = query
	variables["count"] = 20
	variables["product"] = product
	variables["querySource"] = "typed_query"
	delete(variables, "cursor")
	features := operation.Features
	if len(features) == 0 {
		features = tweetFeatures
	}
	fieldToggles := operation.FieldToggles
	if len(fieldToggles) == 0 {
		fieldToggles = searchFieldToggles
	}
	seenPosts := map[string]bool{}
	seenCursors := map[string]bool{}
	posts := make([]model.Post, 0, min(maxPosts, 256))
	emptyPages := 0
	for page := 1; len(posts) < maxPosts; page++ {
		if ctx.Err() != nil {
			return posts, ctx.Err()
		}
		if progress != nil {
			progress(fmt.Sprintf("Fetching X search page %d · %d posts", page, len(posts)), min(94, 5+page*2), nil)
		}
		payload, _, err := c.DoWithHeaders(
			ctx,
			"SearchTimeline",
			variables,
			features,
			fieldToggles,
			"https://x.com/search?q="+url.QueryEscape(query),
			safeSearchHeaders(operation.Headers),
		)
		if err != nil {
			return posts, err
		}
		added := 0
		for _, post := range ExtractPosts(payload, query) {
			if post.ID == "" || seenPosts[post.ID] {
				continue
			}
			seenPosts[post.ID] = true
			posts = append(posts, post)
			added++
			if progress != nil {
				copy := post
				progress(fmt.Sprintf("Extracted %d unique post(s)", len(posts)), min(94, 8+len(posts)), &copy)
			}
			if len(posts) >= maxPosts {
				break
			}
		}
		cursor := findCursor(payload, "Bottom")
		if cursor == "" || seenCursors[cursor] {
			break
		}
		seenCursors[cursor] = true
		variables["cursor"] = cursor
		if added == 0 {
			emptyPages++
		} else {
			emptyPages = 0
		}
		if emptyPages >= 4 {
			break
		}
		select {
		case <-ctx.Done():
			return posts, ctx.Err()
		case <-time.After(time.Duration(delaySeconds) * time.Second):
		}
	}
	if progress != nil {
		progress(fmt.Sprintf("X search complete · %d unique post(s)", len(posts)), 100, nil)
	}
	return posts, nil
}

// Captured authorization, CSRF and transaction headers are tied to the old
// browser request. Replaying them would overwrite the fresh AppData session.
func safeSearchHeaders(captured map[string]string) map[string]string {
	allowed := map[string]bool{
		"accept-language":           true,
		"x-twitter-active-user":     true,
		"x-twitter-auth-type":       true,
		"x-twitter-client-language": true,
	}
	result := map[string]string{}
	for key, value := range captured {
		key = strings.ToLower(strings.TrimSpace(key))
		if allowed[key] && strings.TrimSpace(value) != "" {
			result[key] = value
		}
	}
	return result
}

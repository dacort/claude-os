package creative

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"time"
)

const usageEndpoint = "https://api.anthropic.com/api/oauth/usage"

// UsageWindow represents a single rate limit window.
type UsageWindow struct {
	Utilization float64 `json:"utilization"`
	ResetsAt    string  `json:"resets_at"`
}

// UsageLimits is the response from the Anthropic OAuth usage API.
type UsageLimits struct {
	FiveHour     *UsageWindow `json:"five_hour"`
	SevenDay     *UsageWindow `json:"seven_day"`
	SevenDaySon  *UsageWindow `json:"seven_day_sonnet"`
}

// FetchUsage queries the Anthropic OAuth usage endpoint.
func FetchUsage(ctx context.Context, oauthToken string) (*UsageLimits, error) {
	if oauthToken == "" {
		return nil, fmt.Errorf("no OAuth token available")
	}

	reqCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	req, err := http.NewRequestWithContext(reqCtx, "GET", usageEndpoint, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+oauthToken)
	req.Header.Set("Accept", "application/json")
	req.Header.Set("anthropic-beta", "oauth-2025-04-20")
	req.Header.Set("User-Agent", "claude-os-controller/1.0")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("usage API request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("usage API returned %d", resp.StatusCode)
	}

	var limits UsageLimits
	if err := json.NewDecoder(resp.Body).Decode(&limits); err != nil {
		return nil, fmt.Errorf("decode usage response: %w", err)
	}
	return &limits, nil
}

// CanUseCreativeTime checks if there's enough headroom in both windows
// to justify a Workshop session. Returns false with a reason if usage is too high.
func CanUseCreativeTime(ctx context.Context, oauthToken string, maxUtilization float64) (bool, string) {
	limits, err := FetchUsage(ctx, oauthToken)
	if err != nil {
		slog.Warn("workshop: could not check usage limits, proceeding cautiously", "error", err)
		// If we can't check, allow but log the warning
		return true, ""
	}

	if limits.FiveHour != nil {
		slog.Info("workshop: usage check",
			"5h_utilization", limits.FiveHour.Utilization,
			"5h_resets_at", limits.FiveHour.ResetsAt,
		)
		if limits.FiveHour.Utilization >= maxUtilization {
			return false, fmt.Sprintf("5h window at %.0f%% (max %.0f%% for creative)", limits.FiveHour.Utilization, maxUtilization)
		}
	}

	if limits.SevenDay != nil {
		slog.Info("workshop: usage check",
			"7d_utilization", limits.SevenDay.Utilization,
			"7d_resets_at", limits.SevenDay.ResetsAt,
		)
		if limits.SevenDay.Utilization >= maxUtilization {
			return false, fmt.Sprintf("7d window at %.0f%% (max %.0f%% for creative)", limits.SevenDay.Utilization, maxUtilization)
		}
	}

	return true, ""
}

package governance

import (
	"context"
	"fmt"
	"strconv"
	"time"

	"github.com/redis/go-redis/v9"
)

type Limits struct {
	DailyTokenLimit     int64   `yaml:"daily_token_limit"`
	WeeklyTokenLimit    int64   `yaml:"weekly_token_limit"`
	ReservePercentage   int     `yaml:"reserve_percentage"`
	MaxTokensPerJob     int64   `yaml:"max_tokens_per_job"`
	CreativeTokenBudget int64   `yaml:"creative_token_budget"`
	DailyBurstBudget    float64 `yaml:"daily_burst_budget"`
	BurstWarningPct     int     `yaml:"burst_warning_pct"`
}

type Governor struct {
	rdb    *redis.Client
	limits Limits
}

func New(rdb *redis.Client, limits Limits) *Governor {
	return &Governor{rdb: rdb, limits: limits}
}

func (g *Governor) dailyKey() string {
	return fmt.Sprintf("claude-os:tokens:daily:%s", time.Now().UTC().Format("2006-01-02"))
}

func (g *Governor) weeklyKey() string {
	year, week := time.Now().UTC().ISOWeek()
	return fmt.Sprintf("claude-os:tokens:weekly:%d-W%02d", year, week)
}

func (g *Governor) burstKey() string {
	return fmt.Sprintf("claude-os:burst:daily:%s", time.Now().UTC().Format("2006-01-02"))
}

func (g *Governor) effectiveDailyLimit() int64 {
	return g.limits.DailyTokenLimit * int64(100-g.limits.ReservePercentage) / 100
}

func (g *Governor) RecordTokenUsage(ctx context.Context, tokens int64) error {
	pipe := g.rdb.Pipeline()
	pipe.IncrBy(ctx, g.dailyKey(), tokens)
	pipe.Expire(ctx, g.dailyKey(), 48*time.Hour)
	pipe.IncrBy(ctx, g.weeklyKey(), tokens)
	pipe.Expire(ctx, g.weeklyKey(), 8*24*time.Hour)
	_, err := pipe.Exec(ctx)
	return err
}

func (g *Governor) getDailyUsage(ctx context.Context) int64 {
	val, err := g.rdb.Get(ctx, g.dailyKey()).Int64()
	if err != nil {
		return 0
	}
	return val
}

func (g *Governor) CanDispatch(ctx context.Context, priority string) (bool, string) {
	used := g.getDailyUsage(ctx)
	limit := g.effectiveDailyLimit()

	if limit == 0 {
		return true, ""
	}

	pct := float64(used) / float64(limit) * 100

	switch priority {
	case "creative":
		if pct >= 70 {
			return false, fmt.Sprintf("creative blocked: %.0f%% of daily limit used", pct)
		}
		creativeKey := fmt.Sprintf("claude-os:tokens:creative:%s", time.Now().UTC().Format("2006-01-02"))
		creativeUsed, _ := g.rdb.Get(ctx, creativeKey).Int64()
		if creativeUsed >= g.limits.CreativeTokenBudget && g.limits.CreativeTokenBudget > 0 {
			return false, "creative token budget exhausted"
		}
	case "normal":
		if pct >= 85 {
			return false, fmt.Sprintf("normal blocked: %.0f%% of daily limit used", pct)
		}
	case "high":
		if pct >= 95 {
			return false, fmt.Sprintf("high blocked: %.0f%% of daily limit used", pct)
		}
	}

	return true, ""
}

func (g *Governor) RecordBurstSpend(ctx context.Context, amount float64) error {
	cents := int64(amount * 100)
	pipe := g.rdb.Pipeline()
	pipe.IncrBy(ctx, g.burstKey(), cents)
	pipe.Expire(ctx, g.burstKey(), 48*time.Hour)
	_, err := pipe.Exec(ctx)
	return err
}

func (g *Governor) CanBurst(ctx context.Context) bool {
	if g.limits.DailyBurstBudget <= 0 {
		return true
	}
	val, err := g.rdb.Get(ctx, g.burstKey()).Result()
	if err != nil {
		return true
	}
	cents, _ := strconv.ParseInt(val, 10, 64)
	spent := float64(cents) / 100
	threshold := g.limits.DailyBurstBudget * float64(g.limits.BurstWarningPct) / 100
	return spent < threshold
}

func (g *Governor) GetUsageSummary(ctx context.Context) map[string]interface{} {
	daily := g.getDailyUsage(ctx)
	weekly, _ := g.rdb.Get(ctx, g.weeklyKey()).Int64()
	burstCents, _ := g.rdb.Get(ctx, g.burstKey()).Int64()

	return map[string]interface{}{
		"daily_tokens_used":  daily,
		"daily_token_limit":  g.effectiveDailyLimit(),
		"weekly_tokens_used": weekly,
		"weekly_token_limit": g.limits.WeeklyTokenLimit,
		"daily_burst_spent":  float64(burstCents) / 100,
		"daily_burst_budget": g.limits.DailyBurstBudget,
	}
}

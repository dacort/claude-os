package governance

import (
	"context"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func setupTestRedis(t *testing.T) *redis.Client {
	t.Helper()
	mr := miniredis.RunT(t)
	return redis.NewClient(&redis.Options{Addr: mr.Addr()})
}

func TestRecordAndCheckTokens(t *testing.T) {
	rdb := setupTestRedis(t)
	g := New(rdb, Limits{
		DailyTokenLimit:     1000,
		WeeklyTokenLimit:    5000,
		ReservePercentage:   30,
		MaxTokensPerJob:     500,
		CreativeTokenBudget: 200,
	})
	ctx := context.Background()

	// Effective limit is 700 (1000 * 70%)
	allowed, reason := g.CanDispatch(ctx, "normal")
	if !allowed {
		t.Errorf("expected dispatch allowed, got denied: %s", reason)
	}

	// Record 600 tokens — 600/700 = 85.7% of effective limit
	g.RecordTokenUsage(ctx, 600)

	// Normal should be blocked at 85%
	allowed, _ = g.CanDispatch(ctx, "normal")
	if allowed {
		t.Error("expected normal dispatch blocked at 85% of effective limit")
	}

	// Creative should also be blocked (>70%)
	allowed, _ = g.CanDispatch(ctx, "creative")
	if allowed {
		t.Error("expected creative dispatch blocked at 85%")
	}

	// High should still be allowed (<95%)
	allowed, _ = g.CanDispatch(ctx, "high")
	if !allowed {
		t.Error("expected high dispatch allowed at 85%")
	}
}

func TestBurstBudget(t *testing.T) {
	rdb := setupTestRedis(t)
	g := New(rdb, Limits{
		DailyTokenLimit:  1_000_000,
		WeeklyTokenLimit: 5_000_000,
		DailyBurstBudget: 5.00,
		BurstWarningPct:  80,
	})
	ctx := context.Background()

	g.RecordBurstSpend(ctx, 4.50)

	canBurst := g.CanBurst(ctx)
	if canBurst {
		t.Error("expected burst blocked at 90% of budget")
	}
}

func TestEffectiveLimitWithReserve(t *testing.T) {
	rdb := setupTestRedis(t)
	g := New(rdb, Limits{
		DailyTokenLimit:   1000,
		ReservePercentage: 30,
	})
	_ = rdb // keep reference

	effective := g.effectiveDailyLimit()
	if effective != 700 {
		t.Errorf("expected effective limit 700, got %d", effective)
	}
}

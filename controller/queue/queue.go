package queue

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

type Status string

const (
	StatusPending   Status = "pending"
	StatusRunning   Status = "running"
	StatusCompleted Status = "completed"
	StatusFailed    Status = "failed"
)

type Priority int

const (
	PriorityCreative Priority = 0
	PriorityNormal   Priority = 10
	PriorityHigh     Priority = 20
)

type Task struct {
	ID          string   `json:"id"`
	Title       string   `json:"title"`
	Description string   `json:"description"`
	TargetRepo  string   `json:"target_repo"`
	Profile     string   `json:"profile"`
	Priority    Priority `json:"priority"`
	Status      Status   `json:"status"`
	Result      string   `json:"result,omitempty"`
	CreatedAt   time.Time `json:"created_at"`
	StartedAt   time.Time `json:"started_at,omitempty"`
	FinishedAt  time.Time `json:"finished_at,omitempty"`
	TokensUsed  int64    `json:"tokens_used,omitempty"`
}

const (
	keyQueue = "claude-os:queue"
	keyTask  = "claude-os:task:%s"
)

type Queue struct {
	rdb *redis.Client
}

func New(rdb *redis.Client) *Queue {
	return &Queue{rdb: rdb}
}

func (q *Queue) Enqueue(ctx context.Context, task *Task) error {
	if task.CreatedAt.IsZero() {
		task.CreatedAt = time.Now().UTC()
	}
	task.Status = StatusPending

	data, err := json.Marshal(task)
	if err != nil {
		return fmt.Errorf("marshal task: %w", err)
	}

	pipe := q.rdb.Pipeline()
	pipe.Set(ctx, fmt.Sprintf(keyTask, task.ID), data, 0)
	pipe.ZAdd(ctx, keyQueue, redis.Z{
		Score:  float64(task.Priority),
		Member: task.ID,
	})
	_, err = pipe.Exec(ctx)
	return err
}

func (q *Queue) Dequeue(ctx context.Context) (*Task, error) {
	results, err := q.rdb.ZRevRangeByScore(ctx, keyQueue, &redis.ZRangeBy{
		Min:   "-inf",
		Max:   "+inf",
		Count: 1,
	}).Result()
	if err != nil {
		return nil, fmt.Errorf("zrevrange: %w", err)
	}
	if len(results) == 0 {
		return nil, nil
	}

	taskID := results[0]
	removed, err := q.rdb.ZRem(ctx, keyQueue, taskID).Result()
	if err != nil {
		return nil, fmt.Errorf("zrem: %w", err)
	}
	if removed == 0 {
		return nil, nil
	}

	task, err := q.Get(ctx, taskID)
	if err != nil {
		return nil, err
	}

	task.Status = StatusRunning
	task.StartedAt = time.Now().UTC()
	return task, q.save(ctx, task)
}

func (q *Queue) Get(ctx context.Context, id string) (*Task, error) {
	data, err := q.rdb.Get(ctx, fmt.Sprintf(keyTask, id)).Bytes()
	if err != nil {
		return nil, fmt.Errorf("get task %s: %w", id, err)
	}
	var task Task
	if err := json.Unmarshal(data, &task); err != nil {
		return nil, fmt.Errorf("unmarshal task: %w", err)
	}
	return &task, nil
}

func (q *Queue) UpdateStatus(ctx context.Context, id string, status Status, result string) error {
	task, err := q.Get(ctx, id)
	if err != nil {
		return err
	}
	task.Status = status
	task.Result = result
	if status == StatusCompleted || status == StatusFailed {
		task.FinishedAt = time.Now().UTC()
	}
	return q.save(ctx, task)
}

func (q *Queue) save(ctx context.Context, task *Task) error {
	data, err := json.Marshal(task)
	if err != nil {
		return fmt.Errorf("marshal task: %w", err)
	}
	return q.rdb.Set(ctx, fmt.Sprintf(keyTask, task.ID), data, 0).Err()
}

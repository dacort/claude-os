package comms

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

// FileChannel writes blocked-task notifications as Markdown files under a
// directory (typically tasks/blocked/). It is write-only: Poll always returns
// nil. Close removes the file.
type FileChannel struct {
	dir string
}

// NewFileChannel creates a FileChannel that writes files to dir.
// The directory is created on first Notify if it does not exist.
func NewFileChannel(dir string) *FileChannel {
	return &FileChannel{dir: dir}
}

// Notify writes tasks/blocked/<task-id>.md with YAML frontmatter.
// If the file already exists the call is a no-op (dedup).
func (f *FileChannel) Notify(_ context.Context, msg Message) error {
	if err := os.MkdirAll(f.dir, 0755); err != nil {
		return fmt.Errorf("comms/file: mkdir %s: %w", f.dir, err)
	}

	path := filepath.Join(f.dir, msg.TaskID+".md")

	// Dedup: skip if the file already exists.
	if _, err := os.Stat(path); err == nil {
		return nil
	}

	created := time.Now().UTC().Format(time.RFC3339)
	content := fmt.Sprintf(`---
type: %s
task_id: %s
project: %s
created: %s
---

# %s

%s
`, msg.Type, msg.TaskID, msg.Project, created, msg.Title, msg.Body)

	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		return fmt.Errorf("comms/file: write %s: %w", path, err)
	}
	return nil
}

// Poll is a no-op for FileChannel — it is write-only for now.
func (f *FileChannel) Poll(_ context.Context) ([]Response, error) {
	return nil, nil
}

// Close removes the blocked file for id, resolving the notification.
// Returns nil if the file does not exist (idempotent).
func (f *FileChannel) Close(_ context.Context, id string) error {
	path := filepath.Join(f.dir, id+".md")
	if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("comms/file: remove %s: %w", path, err)
	}
	return nil
}

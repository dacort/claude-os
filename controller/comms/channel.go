package comms

import (
	"context"
	"errors"
)

// MessageType classifies what kind of human attention a message needs.
type MessageType string

const (
	NeedsHuman     MessageType = "needs-human"
	ProjectUpdate  MessageType = "project-update"
	DecisionNeeded MessageType = "decision-needed"
)

// Message is a notification sent from a worker or the controller to a human.
type Message struct {
	ID      string
	Title   string
	Body    string
	Project string
	TaskID  string
	Type    MessageType
	Mentions []string
}

// Response is a human reply to a Message.
type Response struct {
	MessageID string
	Author    string
	Body      string
	Resolved  bool
}

// Channel is a transport for sending notifications and receiving replies.
type Channel interface {
	// Notify sends a message through this channel.
	Notify(ctx context.Context, msg Message) error
	// Poll returns any new responses since the last call. Returns nil for
	// write-only channels.
	Poll(ctx context.Context) ([]Response, error)
	// Close marks a message thread resolved and removes any local state for id.
	Close(ctx context.Context, id string) error
}

// Manager fans out Notify/Close to all registered channels and merges Poll
// results from all of them.
type Manager struct {
	channels []Channel
}

// NewManager creates a Manager that broadcasts to the given channels.
func NewManager(channels ...Channel) *Manager {
	return &Manager{channels: channels}
}

// Notify sends msg to every registered channel. All channels are attempted;
// errors are collected and joined.
func (m *Manager) Notify(ctx context.Context, msg Message) error {
	var errs []error
	for _, ch := range m.channels {
		if err := ch.Notify(ctx, msg); err != nil {
			errs = append(errs, err)
		}
	}
	return errors.Join(errs...)
}

// Poll collects responses from every channel and returns them merged.
// Returns on the first error.
func (m *Manager) Poll(ctx context.Context) ([]Response, error) {
	var all []Response
	for _, ch := range m.channels {
		responses, err := ch.Poll(ctx)
		if err != nil {
			return nil, err
		}
		all = append(all, responses...)
	}
	return all, nil
}

// Close resolves id on every registered channel.
func (m *Manager) Close(ctx context.Context, id string) error {
	var errs []error
	for _, ch := range m.channels {
		if err := ch.Close(ctx, id); err != nil {
			errs = append(errs, err)
		}
	}
	return errors.Join(errs...)
}

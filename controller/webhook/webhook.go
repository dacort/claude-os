package webhook

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"strings"
)

type Issue struct {
	Number int    `json:"number"`
	Title  string `json:"title"`
	Body   string `json:"body"`
}

type IssueEvent struct {
	Action string `json:"action"`
	Issue  Issue  `json:"issue"`
}

type Handler struct {
	secret  string
	onIssue func(*IssueEvent)
}

func New(secret string, onIssue func(*IssueEvent)) *Handler {
	return &Handler{secret: secret, onIssue: onIssue}
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "read body", http.StatusBadRequest)
		return
	}

	sig := r.Header.Get("X-Hub-Signature-256")
	if !h.validSignature(sig, body) {
		slog.Warn("invalid webhook signature")
		http.Error(w, "invalid signature", http.StatusForbidden)
		return
	}

	event := r.Header.Get("X-GitHub-Event")
	switch event {
	case "issues":
		var ie IssueEvent
		if err := json.Unmarshal(body, &ie); err != nil {
			slog.Error("parse issue event", "error", err)
			http.Error(w, "parse error", http.StatusBadRequest)
			return
		}
		if ie.Action == "opened" || ie.Action == "edited" {
			h.onIssue(&ie)
		}
	default:
		slog.Debug("ignoring event", "type", event)
	}

	w.WriteHeader(http.StatusOK)
}

func (h *Handler) validSignature(sig string, body []byte) bool {
	if !strings.HasPrefix(sig, "sha256=") {
		return false
	}
	expected := sig[7:]

	mac := hmac.New(sha256.New, []byte(h.secret))
	mac.Write(body)
	actual := hex.EncodeToString(mac.Sum(nil))

	return hmac.Equal([]byte(expected), []byte(actual))
}

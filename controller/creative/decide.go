package creative

// SessionType is the kind of idle-time session the controller dispatches.
type SessionType int

const (
	// SessionMaintenance works the approved issue backlog.
	SessionMaintenance SessionType = iota
	// SessionCreativeSpend is a creative session paid for with one earned credit.
	SessionCreativeSpend
	// SessionCreativeFree is a creative session granted because there is no
	// approved work waiting — the gate only exists when real work is pending.
	SessionCreativeFree
	// SessionIdle dispatches nothing: there is no approved/scoped work and
	// goal-less free time is disabled. The Workshop simply waits.
	SessionIdle
)

// DecideSession implements the chores-before-dessert decision table
// (spec 2026-06-10, section 1). approvedBacklog is the count of open
// octo-approved issues; credits is the current ledger balance.
//
// freeCreativeEnabled gates goal-less "free time" (Phase 0 stop-the-bleed):
// when false and there is no approved work, the result is SessionIdle rather
// than SessionCreativeFree. Earned creative time (SessionCreativeSpend) and
// maintenance (SessionMaintenance) are unaffected by the flag.
func DecideSession(approvedBacklog, credits int, freeCreativeEnabled bool) SessionType {
	if approvedBacklog == 0 {
		if freeCreativeEnabled {
			return SessionCreativeFree
		}
		return SessionIdle
	}
	if credits >= 1 {
		return SessionCreativeSpend
	}
	return SessionMaintenance
}

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
)

// DecideSession implements the chores-before-dessert decision table
// (spec 2026-06-10, section 1). approvedBacklog is the count of open
// octo-approved issues; credits is the current ledger balance.
func DecideSession(approvedBacklog, credits int) SessionType {
	if approvedBacklog == 0 {
		return SessionCreativeFree
	}
	if credits >= 1 {
		return SessionCreativeSpend
	}
	return SessionMaintenance
}

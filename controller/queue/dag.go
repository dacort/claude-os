package queue

import "fmt"

// ValidateDAG checks that a set of task dependencies forms a valid directed
// acyclic graph. Returns an error if there are cycles or references to unknown
// tasks.
//
// tasks maps taskID -> list of taskIDs it depends on.
func ValidateDAG(tasks map[string][]string) error {
	// First: check for references to unknown tasks.
	for id, deps := range tasks {
		for _, dep := range deps {
			if _, ok := tasks[dep]; !ok {
				return fmt.Errorf("task %s depends on unknown task %s", id, dep)
			}
		}
	}

	// Kahn's algorithm: count in-degrees (number of deps each task has),
	// then iteratively peel off zero-in-degree nodes. If any node is never
	// peeled, there's a cycle.
	inDegree := make(map[string]int, len(tasks))
	for id, deps := range tasks {
		inDegree[id] = len(deps)
	}

	// Start with all nodes that have no dependencies.
	var ready []string
	for id, deg := range inDegree {
		if deg == 0 {
			ready = append(ready, id)
		}
	}

	visited := 0
	for len(ready) > 0 {
		// Pop one ready node.
		node := ready[0]
		ready = ready[1:]
		visited++

		// For every task that depends on this node, decrement its in-degree.
		// If it reaches zero, it's now ready.
		for id, deps := range tasks {
			for _, dep := range deps {
				if dep == node {
					inDegree[id]--
					if inDegree[id] == 0 {
						ready = append(ready, id)
					}
				}
			}
		}
	}

	if visited != len(tasks) {
		return fmt.Errorf("dependency cycle detected: %d of %d tasks could be ordered",
			visited, len(tasks))
	}
	return nil
}

// ValidateSubtaskCount returns an error if a plan exceeds the maximum
// number of subtasks.
func ValidateSubtaskCount(tasks map[string][]string, max int) error {
	if len(tasks) > max {
		return fmt.Errorf("plan has %d subtasks, max is %d", len(tasks), max)
	}
	return nil
}

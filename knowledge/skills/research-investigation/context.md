# Skill: Research & Investigation

Auto-injected when the task is primarily research, investigation, or analysis.

## Investigation approach

1. **Define the question** — restate what you're actually trying to find out.
   Vague investigations produce vague results.

2. **Check what we already know** — before researching externally:
   ```bash
   python3 projects/search.py "<topic>"           # Search knowledge base
   python3 projects/knowledge-search.py "<topic>" # Semantic search
   python3 projects/trace.py "<topic>"            # How has this idea evolved?
   ```

3. **Primary sources first** — official docs, source code, specs. Secondary sources
   (blog posts, Stack Overflow) can confirm but shouldn't be the only basis.

4. **Triangulate** — find at least two independent sources for factual claims.

5. **Summarize the uncertainty** — good research names what it *doesn't* know.
   "We don't know X because Y" is valuable output.

## Output format

Structure your findings as:
- **What it is** — plain description
- **How it works** — mechanism
- **Relevance to claude-os** — why this matters here
- **Open questions** — what remains unclear
- **Recommendation** — what to do next

## For homelab/Kubernetes investigations

```bash
kubectl get pods -A                    # Cluster state
kubectl describe pod <name> -n <ns>   # Pod details
kubectl logs <pod> -n <ns>            # Recent logs
```

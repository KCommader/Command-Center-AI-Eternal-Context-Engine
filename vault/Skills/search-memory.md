---
type: skill
status: active
category: memory
trigger: search_memory
description: Semantic search across the entire vault
source: Command Center MCP
---

# search_memory

Performs semantic (meaning-based) vector search across your entire vault using LanceDB. Returns the most relevant notes ranked by similarity — not keyword matching.

## Usage
```
search_memory("your query here")
search_memory("trading strategy risk management", k=10)
search_memory("what did I decide about Python vs Node")
```

## Parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `query` | required | Natural language search query |
| `k` | 5 | Number of results to return |
| `namespaces` | all | Limit to specific namespaces |

## Notes
- Works on vault content even if the engine has been offline (re-indexes on startup)
- Searches Knowledge/, Archive/, and Core/ by default
- Results include: score, source file, tier, content snippet

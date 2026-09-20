# Architecture

## Data flow

```
sensor / log source ──► adapter ──► deterministic analysis ──► Finding[] (source="rule")
                                            │
                                            ├──► compact summary ──► Claude ──► Finding[] (source="claude")
                                            │
                                            └──────────────► AgentReport ──► console | JSON | markdown | webhook
```

Adapters are the only ROS-aware code. Deterministic analysis is pure Python over
dataclasses. Claude receives a summary measured in kilobytes, never a raw stream,
which keeps cost bounded and keeps the prompt inside a context the model can reason
over carefully.

## Why the summary, not the stream

A 10-minute diagnostics window at 1 Hz across 5 nodes is 3,000 messages. Sent raw,
most of the prompt is `level: OK` repeated. Sent as per-node uptime, MTBF, failure
episodes and CPU peaks, it is about 40 lines, and the model spends its attention on
correlation rather than parsing. Each agent does this reduction in the deterministic
half before it prompts.

## Failure behavior

| Failure | Behavior |
|---|---|
| No API key | Offline stub returns the fallback dict; rule findings unaffected |
| API error or timeout | Two retries with backoff, then `RuntimeError` |
| Malformed JSON reply | Fences stripped, first object extracted, else `ValueError` |
| Webhook unreachable | Failure recorded per target; report still printed |

Rule-sourced findings never depend on the model, so a total API outage degrades the
system to a conventional monitor rather than taking it down.

## Adding an agent

1. Create `src/robotops/<name>/` with `sim.py`, the analysis module, and `agent.py`.
2. `agent.analyze(data=None, *, client=None) -> AgentReport` is the only required signature.
3. Register the name in `cli.AGENTS` and `cli._run`.
4. Test the deterministic half. Assert on findings with `source="rule"`, never on model prose.

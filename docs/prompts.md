# Prompt notes

Every agent uses the same pattern: a system prompt holding the domain rules, a user
message holding only the reduced data, and a required JSON shape.

Three things carry most of the quality.

**State the interpretation rules explicitly.** The fusion prompt says that large
odometry residuals with small IMU and LiDAR residuals imply wheel slip. Without that,
the model produces plausible but generic "sensors disagree" prose. With it, the
output names a mechanism a robotics engineer can act on.

**Give the model an out.** The RCA prompt instructs it to say when evidence does not
support a confident root cause, and the schema has an `evidence_gaps` field. An RCA
bot that always produces a confident answer is worse than useless during an incident,
because it will invent a cause on the one occasion the logs genuinely do not contain it.

**Ask for structure, then validate it.** All replies are JSON. `llm._parse_json`
strips fences and extracts the object; agents read fields with `.get()` and tolerate
nulls. No agent string-matches prose to make a decision.

## Cost

Each run is a single call with a summary-sized prompt. At default settings a full
sweep of all five agents is a handful of calls, so a per-minute monitoring loop should
throttle: run the deterministic half continuously, and call Claude only when a rule
finding fires or on a fixed reporting cadence.

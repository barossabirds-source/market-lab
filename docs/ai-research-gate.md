# AI research integration: evidence gate

This is a lightweight, provider-neutral first step towards evaluating AI-generated strategies (including proposals from Vibe-Trading). It does **not** install or trust third-party agent code.

## Workflow
1. An AI or human proposes a falsifiable hypothesis and a fixed rule.
2. Freeze the rule and timestamp before collecting evaluation observations.
3. Capture data source, point-in-time integrity, comparator/no-signal sessions and realistic round-trip costs.
4. Evaluate with `research.agent_gate.evaluate`.
5. Treat `research_candidate` as permission for *further forward research only*, not investment or execution approval.

The gate deliberately fails closed on missing evidence. Its simple average-net-return statistic is a diagnostic, **not** statistical significance, Sharpe, or evidence of causality. Future stages should add drawdown, turnover, confidence intervals, regime breakdowns, multiple-testing corrections and an independently sourced ASX/SPI feed. Never supply fabricated verification flags.

No database migrations, external APIs, secrets or new fees are required. Existing dashboard and scheduled jobs remain unchanged.

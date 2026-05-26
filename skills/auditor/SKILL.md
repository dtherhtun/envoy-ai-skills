# Skill: Envoy Configuration Auditor
# Category: devops
# Description: Analyzes Envoy configuration snippets (YAML/JSON) against production-grade operational best practices to identify performance bottlenecks, resilience gaps, and anti-patterns.

## 🎯 Objective
To elevate configuration quality from merely "syntactically correct" to "operationally sound." This skill automates the role of a senior SRE reviewing traffic management policies.

## 🧠 Mental Model: The Failure Surface Area
The auditor systematically scans the configuration against known failure modes in high-scale proxies:
1.  **Resource Exhaustion:** Improperly sized connection pools leading to thread/file descriptor starvation.
2.  **Cascading Failure:** Lack of appropriate timeout/circuit breaking preventing local service failures from propagating upstream.
3.  **Observability Blind Spots:** Absence of necessary tracing/logging hooks in listener or route definitions.
4.  **Default Risk:** Reliance on implicit defaults which are often unsafe in production.

## ⚙️ Invocation & Workflow
The skill is invoked by providing the raw configuration content.

**Input:** Raw configuration text (YAML or JSON).
**Process:**
1.  **Parse:** Load content into a native Python structure (dict/object).
2.  **Analyze:** Traverse the structure, checking against the rule matrix.
3.  **Report:** Generate a machine-readable diagnostic summary.

**Execution Logic (Internal to the skill):**
The logic MUST iterate over clusters, routes, and listeners. For each element, it checks for the presence of required fields based on the criticality of the component (e.g., `timeout_ms` is critical for `clusters`).

## 📊 Output Contract (Mandatory JSON)
The output *must* be a JSON object matching this schema:

\`\`\`json
{
  "summary": {
    "overall_status": "PASS" | "FAIL" | "WARNING",
    "total_checks": <integer>,
    "failed_checks": <integer>
  },
  "findings": [
    {
      "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
      "check_id": "RES-001",
      "description": "<Detailed explanation of the issue, e.g., 'Connection pool is unbounded on cluster X.'>",
      "recommendation": "<Specific, actionable engineering advice, e.g., 'Set max_connections to 500.'>",
      "location_hint": "path/to/element"
    }
  ]
}
\`\`\`

## ⚖️ Tradeoffs
*   **Strength:** Excellent for hardening standards and identifying systemic risks in config drift.
*   **Limitation:** Cannot infer *intent*. If a configuration is intentionally complex, the Auditor might flag it as non-compliant, requiring human override. It needs excellent domain rules to be useful.

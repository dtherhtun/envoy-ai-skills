# Envoy AI Skills

Production-grade AI skills for working with **Envoy Proxy** (v1.38.0+).  
Designed for use with the Hermes Agent system — structured as reusable procedural knowledge for infrastructure engineers.

## Skills

### `envoy-config-validator`

Automated validation of Envoy listener/filter configurations against a canonical YAML schema.  
Covers: listener setup, route config, filter chain, access logs, health checks, and transport socket settings.

### `envoy-config-auditor`

Security and best-practice audit for Envoy configurations.  
Checks TLS settings, admin interface exposure, auth filter presence, retry/timeout policies, and production hardening patterns.

## Directory Structure

```
envoy-ai-skills/
├── README.md
├── requirements.txt
└── skills/
    ├── validator/
    │   ├── validator.py
    │   └── templates/
    │       └── validator_schema.yaml
    └── auditor/
        ├── SKILL.md
        └── auditor.py
```

## Getting Started

Install dependencies:

```bash
pip install -r requirements.txt
```

Use the skills via `skill_manage` or reference the `SKILL.md` files directly in your agent workflows.

## Envoy Version Target

Envoy **v1.38.0** (stable release). Schema and audit rules aligned with this release's config semantics.

## License

MIT

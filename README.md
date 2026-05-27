# Envoy AI Skills

Production-grade AI skills for working with **Envoy Proxy** (v1.38.0+).  
Designed for use with the Hermes Agent system — structured as reusable procedural knowledge for infrastructure engineers.

## Skills

### `envoy-config-validator`

Structural validator for Envoy static bootstrap configurations. Checks YAML/JSON parsing, required fields, nested map validity, and cross-references between routes and clusters.

Run: `python skills/validator/validator.py`

See `skills/validator/SKILL.md` for the full check catalog (NODE, ADMIN, LISTEN, CLUSTER, CONFIG checks with severity levels).

### `envoy-config-auditor`

Production readiness auditor covering security hardening, TLS quality, cluster resilience, and operational best practices.

Run: `python skills/auditor/auditor.py`

See `skills/auditor/SKILL.md` for the full audit check catalog (node, admin, TLS, HCM, cluster, cross-reference).

## Directory Structure

```
envoy-ai-skills/
├── README.md
├── requirements.txt
└── skills/
    ├── validator/
    │   ├── SKILL.md
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

## Envoy Version Target

Envoy **v1.38.0** (stable release). Config parsing, type URLs, and audit rules aligned with this release's v3 API semantics.

## License

MIT

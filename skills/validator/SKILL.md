# envoy-config-validator

## Description

Systematic validation of Envoy proxy configurations against a canonical YAML schema.  
Covers all top-level and nested config sections for Envoy v1.38.0+.

## Trigger

Load when a user:
- Provides an Envoy YAML config (inline, file path, or URL) and asks for validation
- Mentions "validate", "check", or "lint" alongside an Envoy config
- Is setting up a new Envoy deployment or changing routing/traffic logic

## Prerequisites

- `requirements.txt` installed (`pytest`, `requests`, `PyYAML`)
- `skills/validator/validator.py` available
- Schema file: `skills/validator/templates/validator_schema.yaml`

## Step-by-Step

### 1. Load the Config

```bash
# Read config from file
cat /path/to/envoy.yaml
# or from URL
curl -sL <url> | cat
# or from inline text the user provided
```

### 2. Run the Validator

```bash
python skills/validator/validator.py <path-or-url-to-config>
```

The validator performs these checks:

| Section              | Checks                                                                 |
|----------------------|------------------------------------------------------------------------|
| **Static Resources** | Top-level structure: `static_resources` exists                        |
| **Listeners**        | Name present, address/port valid, filter chains defined               |
| **Routes**           | Virtual hosts, route actions (redirect/forward), weighted clusters      |
| **Clusters**         | Name, type (STRICT_DNS, LOGICAL_DNS, ORIGINAL_DST), health checks      |
| **Access Log**       | Configured with output format (FILE, GRPC, or common JSON format)      |
| **Health Check**     | Alive check parameters: path, timeout, interval, healthy/unhealthy thresholds |
| **Transport Socket** | TLS settings where required, sni, certificate chain paths             |

### 3. Report Results

Return a structured validation report:

- **PASS**: Config section is valid
- **WARN**: Section exists but uses non-ideal defaults (e.g., no health check, no access log)
- **FAIL**: Missing required section or invalid value

Example output:

```
=== Envoy Config Validation Report ===
Listeners:     PASS (2 listeners found)
Routes:        PASS (4 route actions defined)
Clusters:      FAIL (cluster "service_api" has no health check)
Access Log:    WARN (configured as FILE, no JSON format)
Transport:     PASS (TLS configured on listener 443)
Overall:       PASS with 2 warnings
```

### 4. Fix Suggestions

For every FAIL or WARN, suggest the minimal YAML fix:

```yaml
# For missing health check on cluster:
- name: service_api
  connect_timeout: 0.25s
  type: STRICT_DNS
  lb_policy: ROUND_ROBIN
  load_assignment:
    cluster_name: service_api
    endpoints:
    - lb_endpoints:
      - endpoint:
          address:
            socket_address:
              address: service-api
              port_value: 8080
  health_checks:
  - timeout: 5s
    interval: 10s
    healthy_threshold: 2
    unhealthy_threshold: 3
    http_health_check:
      path: /healthz
```

## Pitfalls

- Envoy configs often span multiple files or use xDS (CDSD/ADS) — the validator only checks statically defined configs
- Inline listener configs vs full_static_resources vs delta xDS are not handled; clarify which mode the user is using
- Cluster `connect_timeout` defaults to 15s if omitted — this is valid but often too long for user-facing services
- `system_protocols` (envoy_protocols) in Envoy 1.35+ renamed internal protocol support — be aware of version changes

## Edge Cases

- **Bootstrap config vs xDS**: If the user's config is a bootstrap file only, validate the bootstrap sections too
- **Composite configs**: If multiple YAML documents are in one file, validate each one
- **External references**: If `config_source` references an xDS server, note that only static config is validated
- **Version drift**: Envoy 1.38 config schema differs from 1.35 — call out version-specific fields

## Validation Schema

The canonical schema lives in `skills/validator/templates/validator_schema.yaml`. It covers:

- `node`, `layered_runtime`, `admin`, `static_resources`
- Listener structure: `address`, `filter_chains`, `traffic_direction`
- Route structure: `virtual_hosts`, `routes`, `route_action`
- Cluster structure: `connect_timeout`, `lb_policy`, `health_checks`, `transport_socket`
- Access log configuration and formatting

# Skill: Envoy Configuration Validator
# Category: devops
# Description: Validates Envoy configuration manifests (YAML) against structural integrity and known deployment prerequisites.
# Envoy v1.38.0+ native static bootstrap configuration.

## Prerequisites
- Python 3.8+
- `PyYAML` installed (`pip install PyYAML`)

## Invocation

```
python skills/validator/validator.py
```

Passes configuration via stdin or as a file path. Supports YAML and JSON.

## What it validates

### Node section
| Check ID | Severity | Description |
|---|---|---|
| NODE-001 | INFO | Missing node section (acceptable for pure static) |
| NODE-002 | HIGH | Node not a valid map |
| NODE-003 | MEDIUM | Node ID missing |
| NODE-004 | MEDIUM | Node cluster missing (needed for xDS) |

### Admin interface
| Check ID | Severity | Description |
|---|---|---|
| ADMIN-001 | INFO | No admin block (optional) |
| ADMIN-002 | HIGH | Admin not a valid object |
| ADMIN-003 | CRITICAL | Admin bound to 0.0.0.0 (insecure) |
| ADMIN-004 | HIGH | Admin not bound to 127.0.0.1 |
| ADMIN-005 | MEDIUM | Admin port not set |
| ADMIN-006 | HIGH | No allow_paths (all endpoints open) |
| ADMIN-007 | MEDIUM | allow_paths empty/malformed |

### Listener validation
| Check ID | Severity | Description |
|---|---|---|
| LIST-005 | PASS | Listener has a name |
| LIST-006 | HIGH | Listener has no address |
| LIST-007 | CRITICAL | Listener has no port |
| LIST-008 | CRITICAL | Listener has no filter_chains |
| LIST-009 | HIGH | TCP listener has no listen_socket_type |
| LIST-010 | MEDIUM | Listener has no traffic_direction |
| LIST-011 | PASS | Filter chain has at least one filter |
| LIST-012 | HIGH | Filter chain has filter with no typed_config |
| LIST-013 | MEDIUM | Filter chain has no listener_filters |
| LIST-014 | MEDIUM | Filter chain has no filter_chain_match |
| LIST-015 | HIGH | Filter has name but no typed_config |
| LIST-016 | PASS | HTTP connection manager present in filters |
| LIST-017 | HIGH | HCM missing typed_config |
| LIST-018 | HIGH | HCM missing stat_prefix |
| LIST-019 | HIGH | HCM missing http_filters |
| LIST-020 | HIGH | HCM missing route_config |
| LIST-021 | CRITICAL | Router filter missing from http_filters |
| LIST-022 | MEDIUM | Route config has no virtual_hosts |
| LIST-023 | HIGH | Virtual host has no domains |
| LIST-024 | MEDIUM | Virtual host has no routes |
| LIST-025 | HIGH | Route references non-existent cluster |
| LIST-026 | MEDIUM | No socket options configured |
| LIST-027 | LOW | No per-connection-buffer-limit-bytes set |
| LIST-TLS-0 | CRITICAL | HTTPS listener without TLS transport socket |
| LIST-TLS-1 | CRITICAL | HTTPS without TLS certificates |
| LIST-TLS-2 | HIGH | Client certs not required on HTTPS |

### Cluster validation
| Check ID | Severity | Description |
|---|---|---|
| CLUST-001 | CRITICAL | No clusters defined |
| CLUST-002 | HIGH | Cluster has no name |
| CLUST-003 | MEDIUM | Cluster has no type (defaults to STATIC) |
| CLUST-004 | MEDIUM | Cluster type not STATIC |
| CLUST-005 | PASS | Cluster has a name |
| CLUST-006 | PASS | Cluster has connect_timeout |
| CLUST-007 | HIGH | Cluster has no load_assignment |
| CLUST-008 | HIGH | Load assignment has no endpoints |
| CLUST-009 | MEDIUM | No lb_policy set (defaults to ROUND_ROBIN) |
| CLUST-010 | HIGH | Cluster with no endpoints and no EDS |
| CLUST-011 | HIGH | No health_checks configured |
| CLUST-012 | HIGH | No circuit_breakers configured |
| CLUST-013 | MEDIUM | No outlier_detection configured |
| CLUST-014 | PASS | Has http2_protocol_options |
| CLUST-015 | MEDIUM | Has HttpProtocolOptions but no http2_protocol_options |
| CLUST-016 | MEDIUM | Non-EDS cluster missing typed_extension_protocol_options |

### Top-level validation
| Check ID | Severity | Description |
|---|---|---|
| CONFIG-001 | HIGH | Missing static_resources section |
| CONFIG-002 | HIGH | Missing listeners in static_resources |

## Output format

Returns JSON with:
- `summary`: {overall_status, total_checks, passed_checks, failed_checks, critical_findings, high_findings, medium_findings, low_findings}
- `findings`: Array of findings with severity, check_id, description, recommendation, location_hint
- `passed`: Array of passed checks with check_id, description, location_hint

Overall status: `PASS` (no findings), `WARNING` (only MEDIUM/LOW), `FAIL` (any HIGH/CRITICAL).

## Exit codes
- `0`: Script completed (regardless of config validation result)
- `1`: Syntax/parsing error in the configuration

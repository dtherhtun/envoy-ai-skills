# Skill: Envoy Configuration Auditor
# Category: devops
# Description: Audits Envoy configuration manifests for production readiness, security hardening, and operational best practices.
# Envoy v1.38.0+ native static bootstrap configuration.

## Prerequisites
- Python 3.8+
- `PyYAML` installed (`pip install PyYAML`)

## Invocation

```
python skills/auditor/auditor.py
```

Accepts raw config string via stdin or audits a file path.

## Audit areas and checks

### Node section
| Check ID | Severity | Description |
|---|---|---|
| NODE-001 | INFO | No node section (acceptable for static-only) |
| NODE-002 | HIGH | Node not a valid map |
| NODE-003 | MEDIUM | Node ID missing |
| NODE-004 | MEDIUM | Node cluster missing |

### Admin interface
| Check ID | Severity | Description |
|---|---|---|
| ADMIN-001 | INFO | No admin interface (optional) |
| ADMIN-002 | HIGH | Admin not a valid object |
| ADMIN-003 | CRITICAL | Admin bound to 0.0.0.0 or undefined |
| ADMIN-004 | HIGH | Admin not bound to 127.0.0.1 |
| ADMIN-005 | MEDIUM | Admin port not explicitly set |
| ADMIN-006 | HIGH | No allow_paths configured |
| ADMIN-007 | MEDIUM | allow_paths empty or malformed |

### Listener best practices
| Check ID | Severity | Description |
|---|---|---|
| LST-ADR-* | HIGH | Invalid traffic_direction |
| LST-ADR-* | MEDIUM | No traffic_direction set |

### Downstream TLS
| Check ID | Severity | Description |
|---|---|---|
| TLS-CTX-* | HIGH | Missing common_tls_context |
| TLS-MIN-* | CRITICAL | TLS min protocol 1.0/1.1 (RFC 8996) |
| TLS-MIN-* | MEDIUM | TLS min protocol not set (defaults to 1.2) |
| TLS-CIPHER-* | HIGH | Weak ciphers (RC4, DES, 3DES, anon, null) |
| TLS-CERT-* | HIGH | Certificate missing certificate_chain |
| TLS-KEY-* | HIGH | Certificate missing private_key |
| TLS-NOCERT-* | HIGH | No server certificates (TLS cannot function) |
| TLS-SDS-* | PASS | Certificates via SDS |
| TLS-mTLS-* | PASS | Client certificate required |
| TLS-NOMTLS-* | MEDIUM | Client certs not required on HTTPS listener |
| TLS-ALPN-* | PASS | ALPN protocols configured |
| TLS-SESS-* | LOW | No session ticket keys |

### HTTP Connection Manager
| Check ID | Severity | Description |
|---|---|---|
| HCM-STAT-* | MEDIUM | Missing stat_prefix |
| HCM-ROUTE-* | HIGH | Missing route_config |
| HCM-VH-* | HIGH | No virtual_hosts |
| HCM-ROUTE-*-N | MEDIUM | Virtual host has no routes |
| HCM-HFILTER-* | HIGH | Missing http_filters |
| HCM-NOROUTER-* | CRITICAL | Router filter missing from http_filters |
| HCM-ACCESSLOG-* | MEDIUM | No access_log configured |
| HCM-CODEC-* | PASS/INFO | Codec type configured or default |
| HCM-TIMEOUT-* | LOW | No stream_idle_timeout |
| HCM-VH-* | PASS | Virtual hosts configured |
| HCM-ROUTER-* | PASS | Router present in http_filters |

### Cluster best practices
| Check ID | Severity | Description |
|---|---|---|
| CLUST-TIMEOUT-* | HIGH | No connect_timeout (defaults to 15s) |
| CLUST-HC-* | HIGH | No active health checks |
| CLUST-HC-INT-* | MEDIUM | Health check missing interval |
| CLUST-HC-TOUT-* | MEDIUM | Health check missing timeout |
| CLUST-CB-* | HIGH | No circuit breakers |
| CLUST-OD-* | MEDIUM | No outlier_detection |
| CLUST-PROTO-* | PASS | Has HttpProtocolOptions |
| CLUST-PROTO-MISS-* | MEDIUM | Missing HttpProtocolOptions (non-EDS) |
| CLUST-UPCERT-* | HIGH | Upstream TLS no cert validation |
| CLUST-UPCERT-* | PASS | Upstream TLS cert verification set |
| CLUST-SNI-* | PASS | Upstream TLS has SNI |
| CLUST-NOSNI-* | MEDIUM | Upstream TLS no SNI |
| CLUST-TYPE-* | HIGH | Cluster uses DownstreamTlsContext |
| CLUST-NENDPOINT-* | CRITICAL | No endpoints defined |

### Cross-references
| Check ID | Severity | Description |
|---|---|---|
| ROUTE-XREF-* | CRITICAL | Route references undefined cluster |

## Audit categories

### Security
- Admin interface must bind to localhost (127.0.0.1), never 0.0.0.0
- Admin must use allow_paths
- TLS 1.2 minimum (TLS 1.0/1.1 are deprecated per RFC 8996)
- No weak ciphers (RC4, DES, 3DES, anonymous, null)
- Server certificates must be present with chain + private_key
- Client certificates required on inbound HTTPS listeners (mTLS)
- Upstream TLS must have validation context (trusted_ca or SDS)

### Production readiness
- connect_timeout must be short (0.25s–1s), never 15s default
- Active health checks required with proper interval/timeout
- Circuit breakers for cascading failure protection
- Outlier detection for passive failure detection
- HttpProtocolOptions for HTTP/1.1 to HTTP/2 upgrade

### Operational
- Access logs for troubleshooting
- Node ID set for proxy identity
- Traffic direction set for sidecar clarity
- Stream idle timeout appropriate for traffic pattern
- Session ticket keys for TLS session resumption

## Output format

Same JSON structure as the validator:
- `summary`: {overall_status, total_checks, passed_checks, failed_checks, critical_findings, high_findings, medium_findings, low_findings}
- `findings`: Array of findings with severity, check_id, description, recommendation, location_hint
- `passed`: Array of passed checks

## Exit codes
- `0`: Script completed
- `1`: Syntax/parsing error

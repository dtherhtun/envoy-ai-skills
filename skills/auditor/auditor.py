# Skill: Envoy Configuration Auditor
# Category: devops
# Description: Analyzes Envoy configuration snippets against production-grade operational best practices to identify performance bottlenecks, resilience gaps, and anti-patterns.

import yaml
import json
import logging
from typing import Dict, Any, List, Union

# --- Setup ---
logger = logging.getLogger("EnvoyAuditor")
logger.setLevel(logging.INFO)

# Define known policies/rulesets (The intelligence layer)
AUDIT_RULES = {
    "RES-001": {
        "name": "Cluster Timeout Setting",
        "severity": "CRITICAL",
        "description": "External-facing clusters must define a connection timeout to prevent resource exhaustion.",
        "check_function": "check_cluster_timeout"
    },
    "PERF-002": {
        "name": "Connection Pool Sizing",
        "severity": "HIGH",
        "description": "Connection pool limits (max_connections) should be explicitly set for production services.",
        "check_function": "check_cluster_pool_size"
    },
    "OBS-003": {
        "name": "Health Check Presence",
        "severity": "MEDIUM",
        "description": "All exposed clusters should specify a health check mechanism for readiness/liveness.",
        "check_function": "check_health_check"
    }
}

class EnvoyAuditor:
    """
    Analyzes configuration content against codified operational rules.
    """
    def __init__(self):
        self.findings: List[Dict[str, Any]] = []

    def _load_config(self, config_content: str) -> Union[Dict[str, Any], None]:
        """Detects and loads config as YAML or JSON."""
        config_content = config_content.strip()
        if config_content.startswith('{') or config_content.startswith('['):
            try:
                return json.loads(config_content)
            except json.JSONDecodeError:
                return None
        else:
            try:
                return yaml.safe_load(config_content)
            except yaml.YAMLError:
                return None

    # --- Check Implementations ---
    
    def check_cluster_timeout(self, config: Dict[str, Any], resource_type: str) -> bool:
        """Checks if a cluster definition has explicit timeout configuration."""
        # This is a highly simplified check; real Envoy configs are much deeper.
        clusters = config.get("spec", {}).get("clusters", [])
        for cluster in clusters:
            if "timeout_ms" not in cluster:
                self.findings.append({
                    "severity": "CRITICAL",
                    "check_id": "RES-001",
                    "description": "Cluster lacks explicit timeout setting.",
                    "recommendation": "Set 'timeout_ms' for predictable service failure behavior.",
                    "location_hint": f"spec.clusters[*].timeout_ms"
                })
                return False
        return True

    def check_cluster_pool_size(self, config: Dict[str, Any], resource_type: str) -> bool:
        """Checks for explicit connection pool sizing."""
        clusters = config.get("spec", {}).get("clusters", [])
        for cluster in clusters:
            if "max_connections" not in cluster:
                self.findings.append({
                    "severity": "HIGH",
                    "check_id": "PERF-002",
                    "description": "Connection pool size is not bounded.",
                    "recommendation": "Set 'max_connections' to prevent resource saturation.",
                    "location_hint": f"spec.clusters[*].max_connections"
                })
                return False
        return True

    def check_health_check(self, config: Dict[str, Any], resource_type: str) -> bool:
        """Checks if a cluster has an active health check definition."""
        clusters = config.get("spec", {}).get("clusters", [])
        for cluster in clusters:
            if "health_check" not in cluster:
                self.findings.append({
                    "severity": "MEDIUM",
                    "check_id": "OBS-003",
                    "description": "Cluster is missing an explicit health check.",
                    "recommendation": "Define 'health_check' for robust service discovery and traffic draining.",
                    "location_hint": f"spec.clusters[*].health_check"
                })
                return False
        return True

    def run_audit(self, config_content: str) -> Dict[str, Any]:
        """
        Executes the full audit against the provided configuration content.
        """
        config = self._load_config(config_content)
        
        if not config:
            return {"summary": {"overall_status": "FAIL", "total_checks": 0, "failed_checks": 1}, "findings": [{"severity": "CRITICAL", "check_id": "PARSE-001", "description": "Input could not be parsed as YAML or JSON.", "recommendation": "Check syntax.", "location_hint": "input"}]}

        resource_type = config.get("kind")
        
        if resource_type != "Gateway":
            # Auditor is specialized for the Gateway/ServiceMesh layer
            return {"summary": {"overall_status": "WARNING", "total_checks": 0, "failed_checks": 0}, "findings": [{"severity": "LOW", "check_id": "SCOPE-001", "description": f"Auditor is specialized for 'Gateway' resources. Received {resource_type}.", "recommendation": "Consider using the Validator skill for this type.", "location_hint": "root"}]}

        self.findings = []
        
        # Execute all codified checks
        self.check_cluster_timeout(config, resource_type)
        self.check_cluster_pool_size(config, resource_type)
        self.check_health_check(config, resource_type)
        
        # Final Report Generation
        failed_count = len(self.findings)
        status = "PASS"
        if failed_count > 0:
            status = "FAIL" if failed_count >= 2 else "WARNING"

        return {
            "summary": {
                "overall_status": status,
                "total_checks": 3,
                "failed_checks": failed_count
            },
            "findings": self.findings
        }

# Exposed function signature for skill usage
def execute_audit(config_content: str) -> Dict[str, Any]:
    """
    Public function to call for skill invocation. Accepts raw config string.
    """
    auditor = EnvoyAuditor()
    return auditor.run_audit(config_content)

if __name__ == "__main__":
    # Example usage for internal testing (Requires mock data)
    print("--- Running internal test ---")
    # A configuration that should fail checks RES-001 and PERF-002
    failing_config = """
apiVersion: envoy.config.x
kind: Gateway
metadata:
  name: production-service
spec:
  routes:
    - match:
        prefix: "/data"
      route:
        cluster: db_cluster
  clusters:
    - name: db_cluster
      type: STATIC
      load_assignment:
        cluster_name: db_cluster
        endpoints:
          - locality: {}
            endpoints:
              - address:
                  socket_address:
                    address: 10.0.0.5
                    port_value: 5432
"""
    print("\n--- Test Case: Failing Config ---")
    print(json.dumps(execute_audit(failing_config), indent=2))
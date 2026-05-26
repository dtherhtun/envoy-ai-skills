# Skill: Envoy Configuration Validator
# Category: devops
# Description: Validates Envoy configuration manifests (YAML/JSON) against structural integrity and known deployment prerequisites.

import yaml
import json
import logging
from typing import Dict, Any, List, Union

# --- Setup ---
logger = logging.getLogger("EnvoyValidator")
logger.setLevel(logging.INFO)

# Define structure expectations for known Envoy resource types (simplified)
# In a production tool, this would load an OpenAPI/JSON Schema definition.
REQUIRED_FIELDS_BY_TYPE = {
    "Gateway": {
        "metadata": {"name": str},
        "spec": {
            "routes": list,
            "clusters": list
        }
    },
    "Cluster": {
        "name": str,
        "load_assignment": {
            "cluster_name": str,
            "endpoints": list # Endpoints are complex, only checking list presence
        }
    }
}

def _load_config(config_content: str) -> Union[Dict[str, Any], Dict[str, Any]]:
    """Detects and loads config as YAML or JSON."""
    config_content = config_content.strip()
    if config_content.startswith('{') or config_content.startswith('['):
        try:
            return json.loads(config_content)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON Parsing Error: {e}")
    else:
        try:
            return yaml.safe_load(config_content)
        except yaml.YAMLError as e:
            raise ValueError(f"YAML Parsing Error: {e}")

def validate_config(config_content: str) -> Dict[str, Any]:
    """
    Main entry point for the skill. Validates content structure.
    Returns a structured report.
    """
    report: Dict[str, Any] = {
        "summary": {"overall_status": "PASS", "total_checks": 0, "failed_checks": 0},
        "findings": []
    }
    
    try:
        config = _load_config(config_content)
        
        # Assuming we are validating a single resource type for simplicity in this skill
        resource_type = config.get("kind")
        metadata = config.get("metadata", {})
        
        if not resource_type or resource_type not in REQUIRED_FIELDS_BY_TYPE:
            report["summary"]["overall_status"] = "FAIL"
            report["findings"].append({
                "severity": "CRITICAL",
                "check_id": "SYN-001",
                "description": "Could not identify a known Envoy resource type.",
                "recommendation": "Ensure the config includes a valid 'kind' field (e.g., 'Gateway', 'Cluster').",
                "location_hint": "root"
            })
            return report

        schema = REQUIRED_FIELDS_BY_TYPE[resource_type]
        report["summary"]["total_checks"] = len(schema)
        
        # 1. Check top-level keys
        for key, expected in schema.items():
            if key not in config:
                report["summary"]["overall_status"] = "FAIL"
                report["summary"]["failed_checks"] += 1
                report["findings"].append({
                    "severity": "CRITICAL",
                    "check_id": "SYN-002",
                    "description": f"Missing required top-level key: '{key}'.",
                    "recommendation": f"Add '{key}' based on the {resource_type} definition.",
                    "location_hint": f"root.{key}"
                })
                continue
            
            actual = config.get(key)
            
            # 2. Check sub-keys and types recursively (simplified for demonstration)
            if isinstance(expected, dict):
                # Check sub-structure (e.g., metadata)
                for sub_key, sub_expected in expected.items():
                    if sub_key not in actual:
                        report["summary"]["overall_status"] = "FAIL"
                        report["summary"]["failed_checks"] += 1
                        report["findings"].append({
                            "severity": "HIGH",
                            "check_id": "SYN-003",
                            "description": f"Required sub-key '{sub_key}' missing under '{key}'.",
                            "recommendation": f"Populate '{sub_key}' structure.",
                            "location_hint": f"{key}.{sub_key}"
                        })
            elif not isinstance(actual, expected):
                 report["summary"]["overall_status"] = "FAIL"
                 report["summary"]["failed_checks"] += 1
                 report["findings"].append({
                    "severity": "HIGH",
                    "check_id": "SYN-004",
                    "description": f"Key '{key}' has incorrect type. Expected {expected.__name__ if hasattr(expected, '__name__') else type(expected).__name__}, got {type(actual).__name__}.",
                    "recommendation": "Correct the data type for key '{key}'.",
                    "location_hint": f"root.{key}"
                })
        
        # In a real scenario, we would iterate through routes/clusters here and check them against service mesh invariants.
        
    except ValueError as e:
        report["summary"]["overall_status"] = "FAIL"
        report["summary"]["failed_checks"] = 1
        report["findings"].append({"severity": "CRITICAL", "check_id": "PARSE-001", "description": str(e), "recommendation": "Review syntax/structure.", "location_hint": "input"})
        
    logger.info(f"Validation complete. Status: {report['summary']['overall_status']}")
    return report

# Exposed function signature for skill usage
def execute_validation(config_content: str) -> Dict[str, Any]:
    """
    Public function to call for skill invocation. Accepts raw config string.
    """
    return validate_config(config_content)

if __name__ == "__main__":
    # Example usage is now cleaner
    print("--- Running internal test ---")
    # Test Case 1: Bad YAML
    bad_yaml = "kind: Gateway\nspec: { routes: []"
    print("\n--- Test Case 1: Bad YAML ---")
    print(json.dumps(execute_validation(bad_yaml), indent=2))
    
    # Test Case 2: Good structure (minimal)
    good_yaml = """
apiVersion: envoy.config.x
kind: Gateway
metadata:
  name: frontend
spec:
  routes: []
  clusters: []
"""
    print("\n--- Test Case 2: Minimal Good YAML ---")
    print(json.dumps(execute_validation(good_yaml), indent=2))
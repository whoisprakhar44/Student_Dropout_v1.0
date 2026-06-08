import os
import sys
import json
from pathlib import Path

# Add MCP folder to path
mcp_path = Path(__file__).resolve().parent / "MCP"
sys.path.insert(0, str(mcp_path))

from hive_executor import HiveExecutor

def main():
    config_path = mcp_path / "hive_config.yaml"
    print(f"Loading config from: {config_path}")
    
    # Force enable HIVE/Impala executor for this check
    os.environ["HIVE_MCP_ENABLED"] = "true"
    
    try:
        executor = HiveExecutor(str(config_path))
        print("Connected to Impala.")
        
        # Describe citizen_welfare_schemes
        print("\n--- Columns in curated_datamodels.citizen_welfare_schemes ---")
        res1 = executor.execute("DESCRIBE curated_datamodels.citizen_welfare_schemes;")
        payload1 = json.loads(res1)
        if payload1.get("status") == "success":
            for row in payload1.get("rows", []):
                print(f"{row.get('name') or row.get('col_name')} ({row.get('type') or row.get('data_type')})")
        else:
            print("Error description welfare table:", payload1.get("error_msg"))

        # Describe citizen_health_schemes
        print("\n--- Columns in curated_datamodels.citizen_health_schemes ---")
        res2 = executor.execute("DESCRIBE curated_datamodels.citizen_health_schemes;")
        payload2 = json.loads(res2)
        if payload2.get("status") == "success":
            for row in payload2.get("rows", []):
                print(f"{row.get('name') or row.get('col_name')} ({row.get('type') or row.get('data_type')})")
        else:
            print("Error description health table:", payload2.get("error_msg"))
            
    except Exception as e:
        print("Error during execution:", e)

if __name__ == "__main__":
    main()

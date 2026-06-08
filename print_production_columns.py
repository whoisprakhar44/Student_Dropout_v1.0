#!/usr/bin/env python3
"""
Introspect columns of production tables using PyHive.
"""

import sys

def main():
    host = "dl-dev-cl-mn02.datalake-dev.local"
    port = 10000
    auth = "KERBEROS"
    kerberos_service_name = "hive"

    print(f"Connecting to Hive at {host}:{port} using PyHive (auth={auth}, service={kerberos_service_name})...")
    try:
        from pyhive import hive
        conn = hive.Connection(
            host=host,
            port=port,
            auth=auth,
            kerberos_service_name=kerberos_service_name
        )
    except Exception as e:
        print(f"Error connecting: {e}")
        print("Make sure you run inside the virtualenv and have valid Kerberos tickets (kinit).")
        sys.exit(1)

    cursor = conn.cursor()

    # Apply session settings
    try:
        cursor.execute("SET hive.vectorized.execution.enabled=false")
    except Exception as e:
        print(f"Warning setting session parameter: {e}")

    tables = [
        "curated_datamodels.citizen_address_master",
        "curated_datamodels.citizen_asset_electricity",
        "curated_datamodels.citizen_land",
        "curated_datamodels.citizen_property",
        "curated_datamodels.citizen_bank_accounts",
        "curated_datamodels.citizen_asset_vaahan",
        "curated_datamodels.citizen_utility_connection",
        "curated_datamodels.citizen_family_master"
    ]

    for table in tables:
        print(f"\n--- Columns in {table} ---")
        try:
            cursor.execute(f"DESCRIBE {table}")
            rows = cursor.fetchall()
            for row in rows:
                print(row)
        except Exception as e:
            print(f"Error describing {table}: {e}")

    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()

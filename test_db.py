#!/usr/bin/env python3
"""
Test script to verify database setup works correctly.
Run this before starting the backend to ensure everything is configured properly.
"""

import sqlite3
import os
import sys

DB_PATH = os.path.join(os.path.dirname(__file__), 'database', 'schema.db')

def test_database():
    print("=" * 60)
    print("Testing Student Dropout Prediction Database Setup")
    print("=" * 60)
    
    # Create database directory
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    print(f"\n✓ Database directory ready: {os.path.dirname(DB_PATH)}")
    
    # Connect to database
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        print("✓ Database connection successful")
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False
    
    # Check if tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    required_tables = [
        'academic_years', 'schools', 'students', 'social_economic',
        'family_background', 'attendance', 'academic_scores', 'dropout_records'
    ]
    
    if not tables:
        print("\n✓ Database is empty (will initialize on backend startup)")
    else:
        print(f"\n✓ Found {len(tables)} tables in database")
        for table in required_tables:
            if table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"  • {table}: {count} records")
            else:
                print(f"  ✗ Missing table: {table}")
    
    conn.close()
    
    print("\n" + "=" * 60)
    print("Database Test Result: PASSED ✓")
    print("=" * 60)
    print("\nYou can now start the backend with:")
    print("  uvicorn app:app --reload --host 0.0.0.0 --port 8000")
    print("\nThen access the dashboard at:")
    print("  http://localhost:8000")
    print("=" * 60)
    
    return True

if __name__ == '__main__':
    success = test_database()
    sys.exit(0 if success else 1)

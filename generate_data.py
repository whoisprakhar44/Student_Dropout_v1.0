#!/usr/bin/env python3
"""
Regenerate the curated SQLite sample database.
"""

from create_schema import create_database


def generate_synthetic_data() -> None:
    create_database(replace=True)


if __name__ == "__main__":
    generate_synthetic_data()

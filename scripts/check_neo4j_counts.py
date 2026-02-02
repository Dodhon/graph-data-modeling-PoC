#!/usr/bin/env python3
"""
Quick Neo4j database counts.

Usage:
  PYTHONPATH=. python3 scripts/check_neo4j_counts.py
"""

import os
from dotenv import load_dotenv
from neo4j import GraphDatabase


def main() -> None:
    load_dotenv()

    uri = os.getenv("NEO4J_URI")
    username = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")
    database = os.getenv("NEO4J_DATABASE")

    if not uri or not username or not password:
        print("❌ Missing Neo4j config. Set NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD in .env")
        return

    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        with driver.session(database=database) as session:
            nodes = session.run("MATCH (n) RETURN count(n) AS nodes").single()["nodes"]
            relationships = session.run("MATCH ()-[r]->() RETURN count(r) AS relationships").single()[
                "relationships"
            ]
    finally:
        driver.close()

    print("✅ Neo4j counts")
    print(f"  - Nodes: {nodes}")
    print(f"  - Relationships: {relationships}")


if __name__ == "__main__":
    main()

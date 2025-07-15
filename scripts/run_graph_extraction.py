#!/usr/bin/env python3
"""
Simple runner script to extract knowledge graph from E80 manual
"""

import os
from dotenv import load_dotenv
from src.graph_builder import ManualGraphBuilder

def main():
    print("🚀 Starting Knowledge Graph Extraction from E80 Manual")
    
    # Load environment variables
    load_dotenv()
    
    # Check for required API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ Please set ANTHROPIC_API_KEY in .env file")
        print("Copy .env.example to .env and add your Anthropic API key")
        return
    
    # Initialize builder
    builder = ManualGraphBuilder(
        anthropic_api_key=api_key,
        neo4j_uri=os.getenv("NEO4J_URI"),
        neo4j_username=os.getenv("NEO4J_USERNAME"),
        neo4j_password=os.getenv("NEO4J_PASSWORD")
    )
    
    # Check if manual exists
    manual_path = "data/input/E80_manual_text.txt"
    if not os.path.exists(manual_path):
        print(f"❌ Manual file not found: {manual_path}")
        return
    
    print(f"📖 Processing manual: {manual_path}")
    
    try:
        # Build the graph from entire manual
        result = builder.build_graph_from_manual(manual_path)
        
        # Print results
        print("\n✅ Graph extraction completed!")
        print(f"📊 Statistics:")
        print(f"  - Total chunks processed: {result['total_chunks']}")
        print(f"  - Graph documents created: {result['total_graph_documents']}")
        print(f"  - Total nodes extracted: {result['total_nodes']}")
        print(f"  - Total relationships: {result['total_relationships']}")
        
        # Export to JSON
        if result['graph_documents']:
            output_path = "e80_knowledge_graph.json"
            builder.export_graph_json(result['graph_documents'], output_path)
            print(f"📄 Graph exported to: {output_path}")
        
    except Exception as e:
        print(f"❌ Error during processing: {e}")
        print("Make sure you have:")
        print("1. Valid Anthropic API key in .env")
        print("2. Installed dependencies: pip install -r requirements.txt")

if __name__ == "__main__":
    main()
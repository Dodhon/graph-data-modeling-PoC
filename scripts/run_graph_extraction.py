#!/usr/bin/env python3
"""
Simple runner script to extract knowledge graph from E80 manual
"""

import os
import argparse
from dotenv import load_dotenv
from src.graph_builder import ManualGraphBuilder

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Extract knowledge graph from E80 manual")
    parser.add_argument("--start-chunk", type=int, default=0, 
                       help="Starting chunk index (default: 0)")
    parser.add_argument("--with-temporal-schema", action="store_true",
                       help="Also extract temporal patterns and induce schemas (default: off)")
    parser.add_argument("--save-every", type=int, default=1,
                       help="Save progress every N chunks (default: 1)")
    args = parser.parse_args()
    
    print("🚀 Starting Knowledge Graph Extraction from E80 Manual")
    if args.start_chunk > 0:
        print(f"📍 Starting from chunk {args.start_chunk}")
    
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
        result = builder.build_graph_from_manual(
            manual_path,
            start_chunk=args.start_chunk,
            process_temporal_schema=args.with_temporal_schema,
            save_every=max(1, args.save_every)
        )
        
        # Print results
        print("\n✅ EEC Graph extraction completed!")
        print(f"📊 Statistics:")
        print(f"  - Total chunks processed: {result['total_chunks']}")
        print(f"  - EEC documents created: {result['total_eec_documents']}")
        print(f"  - Total entities extracted: {result['total_entities']}")
        print(f"  - Total events extracted: {result['total_events']}")
        print(f"  - Total concepts extracted: {result['total_concepts']}")
        print(f"  - Total relationships: {result['total_relationships']}")
        
        # Print temporal patterns summary (if computed)
        if result['temporal_patterns'] is not None:
            temporal_patterns = result['temporal_patterns']
            print(f"\n🔄 Temporal Patterns:")
            print(f"  - Diagnostic sequences: {len(temporal_patterns['diagnostic_sequences'])}")
            print(f"  - Causal chains: {len(temporal_patterns['causal_chains'])}")
            print(f"  - Prerequisite graphs: {len(temporal_patterns['prerequisite_graphs'])}")
            print(f"  - Conditional logic: {len(temporal_patterns['conditional_logic'])}")

        # Print schemas summary (if computed)
        if result['schemas'] is not None:
            schemas = result['schemas']
            print(f"\n🏗️ Schemas:")
            print(f"  - Entity hierarchies: {len(schemas['entity_hierarchies'])}")
            print(f"  - Event patterns: {len(schemas['event_patterns'])}")
            print(f"  - Concept networks: {len(schemas['concept_networks'])}")
            print(f"  - Domain schemas: {len(schemas['domain_schemas'])}")
        
        # Export to JSON
        if result['eec_documents']:
            output_path = os.path.join(builder.output_dir, "e80_eec_knowledge_graph.json")
            builder.export_eec_json(result['eec_documents'], output_path)
            print(f"📄 EEC graph exported to: {output_path}")
            if args.with_temporal_schema:
                temporal_path = os.path.join(builder.output_dir, "e80_temporal_patterns.json")
                schema_path = os.path.join(builder.output_dir, "e80_schemas.json")
                print(f"📄 Temporal patterns exported to: {temporal_path}")
                print(f"📄 Schemas exported to: {schema_path}")
        
    except Exception as e:
        print(f"❌ Error during processing: {e}")
        print("Make sure you have:")
        print("1. Valid Anthropic API key in .env")
        print("2. Installed dependencies: pip install -r requirements.txt")

if __name__ == "__main__":
    main()
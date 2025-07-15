#!/usr/bin/env python3
"""
Schema analysis tool to examine discovered entities and relationships
"""

import json
from collections import Counter, defaultdict
from typing import Dict, List, Any

def analyze_graph_schema(json_file: str) -> Dict[str, Any]:
    """Analyze the schema of discovered entities and relationships"""
    
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    # Analyze nodes
    node_types = Counter()
    node_properties = defaultdict(Counter)
    
    for node in data['nodes']:
        node_types[node['type']] += 1
        for prop_key, prop_value in node.get('properties', {}).items():
            if prop_value:  # Only count non-empty properties
                node_properties[node['type']][prop_key] += 1
    
    # Analyze relationships
    relationship_types = Counter()
    relationship_properties = defaultdict(Counter)
    
    for rel in data['relationships']:
        rel_type = rel['type']
        relationship_types[rel_type] += 1
        
        for prop_key, prop_value in rel.get('properties', {}).items():
            if prop_value:  # Only count non-empty properties
                relationship_properties[rel_type][prop_key] += 1
    
    # Analyze relationship patterns
    relationship_patterns = Counter()
    for rel in data['relationships']:
        # Find source and target node types
        source_type = None
        target_type = None
        
        for node in data['nodes']:
            if node['id'] == rel['source']:
                source_type = node['type']
            if node['id'] == rel['target']:
                target_type = node['type']
        
        if source_type and target_type:
            pattern = f"{source_type} -> {rel['type']} -> {target_type}"
            relationship_patterns[pattern] += 1
    
    return {
        'summary': {
            'total_nodes': len(data['nodes']),
            'total_relationships': len(data['relationships']),
            'unique_node_types': len(node_types),
            'unique_relationship_types': len(relationship_types)
        },
        'node_types': dict(node_types.most_common()),
        'node_properties': dict(node_properties),
        'relationship_types': dict(relationship_types.most_common()),
        'relationship_properties': dict(relationship_properties),
        'relationship_patterns': dict(relationship_patterns.most_common(20))
    }

def print_analysis(analysis: Dict[str, Any]):
    """Print formatted analysis results"""
    
    print("=" * 60)
    print("KNOWLEDGE GRAPH SCHEMA ANALYSIS")
    print("=" * 60)
    
    # Summary
    summary = analysis['summary']
    print(f"\n📊 SUMMARY:")
    print(f"  Total Nodes: {summary['total_nodes']}")
    print(f"  Total Relationships: {summary['total_relationships']}")
    print(f"  Unique Node Types: {summary['unique_node_types']}")
    print(f"  Unique Relationship Types: {summary['unique_relationship_types']}")
    
    # Node types
    print(f"\n🏷️  NODE TYPES (Top 15):")
    for node_type, count in list(analysis['node_types'].items())[:15]:
        print(f"  {node_type}: {count}")
    
    # Relationship types
    print(f"\n🔗 RELATIONSHIP TYPES (Top 15):")
    for rel_type, count in list(analysis['relationship_types'].items())[:15]:
        print(f"  {rel_type}: {count}")
    
    # Most common patterns
    print(f"\n🔄 RELATIONSHIP PATTERNS (Top 15):")
    for pattern, count in list(analysis['relationship_patterns'].items())[:15]:
        print(f"  {pattern}: {count}")
    
    # Properties with data
    print(f"\n📋 NODE PROPERTIES WITH DATA:")
    for node_type, props in analysis['node_properties'].items():
        if props:
            print(f"  {node_type}:")
            for prop, count in props.items():
                print(f"    {prop}: {count} nodes")

def main():
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python analyze_schema.py <json_file>")
        return
    
    json_file = sys.argv[1]
    
    try:
        analysis = analyze_graph_schema(json_file)
        print_analysis(analysis)
        
        # Save analysis to file
        output_file = json_file.replace('.json', '_analysis.json')
        with open(output_file, 'w') as f:
            json.dump(analysis, f, indent=2)
        
        print(f"\n💾 Analysis saved to: {output_file}")
        
    except FileNotFoundError:
        print(f"❌ File not found: {json_file}")
    except Exception as e:
        print(f"❌ Error analyzing schema: {e}")

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Test script for Claude-based graph extraction
"""

import os
from dotenv import load_dotenv
from langchain.schema import Document
from langchain_experimental.graph_transformers import LLMGraphTransformer
from langchain_anthropic import ChatAnthropic

def test_claude_connection():
    """Test basic Claude API connection"""
    print("🔍 Testing Claude API connection...")
    
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    
    if not api_key:
        print("❌ No Anthropic API key found")
        return False
    
    try:
        llm = ChatAnthropic(
            api_key=api_key,
            model="claude-3-5-sonnet-20241022",
            temperature=0,
            timeout=30,
            max_retries=2
        )
        
        # Test simple call
        response = llm.invoke("Hello, respond with 'Claude API working'")
        print(f"✅ API Response: {response.content}")
        return True
        
    except Exception as e:
        print(f"❌ API Error: {e}")
        return False

def test_graph_extraction():
    """Test graph extraction on a small sample"""
    print("\n🧪 Testing graph extraction with Claude...")
    
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    
    # Simple test text from your manual
    test_text = """
    E80 Group S.p.A. manufactures the LGV COUNTERBALANCED FORKLIFT VEHICLE.
    The machine model is LCDZ1716 with serial number LCDZ1716.
    The forklift has rear wheel drive and hydraulic lift systems.
    Safety procedures must be followed during maintenance operations.
    Regular maintenance includes checking hydraulic fluid levels.
    """
    
    try:
        llm = ChatAnthropic(
            api_key=api_key,
            model="claude-3-5-sonnet-20241022",
            temperature=0,
            timeout=60,
            max_retries=3
        )
        
        transformer = LLMGraphTransformer(
            llm=llm,
            node_properties=["description", "type"],
            relationship_properties=["context", "description"]
        )
        
        documents = [Document(page_content=test_text)]
        
        print("🔄 Converting to graph documents with Claude...")
        graph_docs = transformer.convert_to_graph_documents(documents)
        
        print(f"✅ Success! Generated {len(graph_docs)} graph documents")
        
        for doc in graph_docs:
            print(f"  Nodes: {len(doc.nodes)}")
            print(f"  Relationships: {len(doc.relationships)}")
            
            # Print some examples
            for node in doc.nodes[:3]:
                print(f"    Node: {node.id} ({node.type})")
            
            for rel in doc.relationships[:3]:
                print(f"    Rel: {rel.source.id} -> {rel.type} -> {rel.target.id}")
        
        return True
        
    except Exception as e:
        print(f"❌ Graph extraction error: {e}")
        return False

def main():
    print("🧪 Testing Claude-based Graph Extraction System\n")
    
    # Test API connection first
    if not test_claude_connection():
        print("\n💡 Troubleshooting tips:")
        print("1. Get Anthropic API key from: https://console.anthropic.com/")
        print("2. Add ANTHROPIC_API_KEY to .env file")
        print("3. Check internet connection")
        return
    
    # Test graph extraction
    if not test_graph_extraction():
        print("\n💡 Graph extraction failed. Check:")
        print("1. LangChain version compatibility")
        print("2. API rate limits")
        return
    
    print("\n🎉 All tests passed! Claude integration working.")
    print("Run: python run_graph_extraction.py")

if __name__ == "__main__":
    main()
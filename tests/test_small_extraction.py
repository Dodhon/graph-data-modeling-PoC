#!/usr/bin/env python3
"""
Test script for small-scale graph extraction to debug connection issues
"""

import os
import time
from dotenv import load_dotenv
from langchain.schema import Document
from langchain_experimental.graph_transformers import LLMGraphTransformer
from langchain_openai import ChatOpenAI

def test_api_connection():
    """Test basic OpenAI API connection"""
    print("🔍 Testing OpenAI API connection...")
    
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("❌ No API key found")
        return False
    
    try:
        llm = ChatOpenAI(
            api_key=api_key,
            model="gpt-4o-mini",
            temperature=0,
            timeout=30,
            max_retries=2
        )
        
        # Test simple call
        response = llm.invoke("Hello, respond with 'API working'")
        print(f"✅ API Response: {response.content}")
        return True
        
    except Exception as e:
        print(f"❌ API Error: {e}")
        return False

def test_graph_extraction():
    """Test graph extraction on a small sample"""
    print("\n🧪 Testing graph extraction...")
    
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    
    # Simple test text from your manual
    test_text = """
    E80 Group S.p.A. manufactures the LGV COUNTERBALANCED FORKLIFT VEHICLE.
    The machine model is LCDZ1716 with serial number LCDZ1716.
    The forklift has rear wheel drive and hydraulic lift systems.
    Safety procedures must be followed during maintenance operations.
    Regular maintenance includes checking hydraulic fluid levels.
    """
    
    try:
        llm = ChatOpenAI(
            api_key=api_key,
            model="gpt-4o-mini",
            temperature=0,
            timeout=60,
            max_retries=3
        )
        
        transformer = LLMGraphTransformer(
            llm=llm,
            allowed_nodes=["Company", "Machine", "Component", "Procedure"],
            allowed_relationships=[
                ("Company", "MANUFACTURES", "Machine"),
                ("Machine", "HAS_COMPONENT", "Component"),
                ("Procedure", "APPLIES_TO", "Machine")
            ]
        )
        
        documents = [Document(page_content=test_text)]
        
        print("🔄 Converting to graph documents...")
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
    print("🧪 Testing Graph Extraction System\n")
    
    # Test API connection first
    if not test_api_connection():
        print("\n💡 Troubleshooting tips:")
        print("1. Check your API key in .env file")
        print("2. Verify API key has sufficient credits")
        print("3. Check internet connection")
        return
    
    # Test graph extraction
    if not test_graph_extraction():
        print("\n💡 Graph extraction failed. Check:")
        print("1. LangChain version compatibility")
        print("2. API rate limits")
        return
    
    print("\n🎉 All tests passed! You can proceed with full extraction.")
    print("Run: python run_graph_extraction.py")

if __name__ == "__main__":
    main()
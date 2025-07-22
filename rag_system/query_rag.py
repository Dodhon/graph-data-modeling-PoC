#!/usr/bin/env python3
"""
Query interface for OpenAI RAG system using Responses API
Allows querying the E80 manual through the new Responses API with file search
"""

import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import time

# Load environment variables
load_dotenv()

class RAGQuery:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("❌ OPENAI_API_KEY not found in .env file")
            sys.exit(1)
        
        self.client = OpenAI(api_key=api_key)
        self.config_path = Path(__file__).parent / "rag_config.json"
        self.previous_response_id = None  # For conversation continuity
        self.load_config()
    
    def load_config(self):
        """Load the saved configuration"""
        if not self.config_path.exists():
            print("❌ Configuration not found. Please run setup_rag.py first.")
            sys.exit(1)
        
        with open(self.config_path, 'r') as f:
            self.config = json.load(f)
        
        print(f"✅ Loaded configuration from: {self.config_path}")
        print(f"📊 Using Vector Store ID: {self.config['vector_store_id']}")
        print(f"🔧 API Type: {self.config.get('api_type', 'responses')}")
    
    def query(self, question):
        """Query the manual using Responses API with file search"""
        try:
            print("🔄 Processing query...")
            
            # Prepare the request
            request_params = {
                "model": self.config.get('model', 'gpt-4o'),
                "input": question,
                "tools": [{
                    "type": "file_search",
                    "vector_store_ids": [self.config['vector_store_id']]
                }]
            }
            
            # Add previous response ID for conversation continuity if available
            if self.previous_response_id:
                request_params["previous_response_id"] = self.previous_response_id
            
            # Make the API call
            response = self.client.responses.create(**request_params)
            
            # Store response ID for conversation continuity
            self.previous_response_id = response.id
            
            # Extract and return the response content
            if response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                return content
            else:
                return "❌ No response received from the API"
                
        except Exception as e:
            return f"❌ Error during query: {e}"
    
    def reset_conversation(self):
        """Reset conversation history"""
        self.previous_response_id = None
        print("🔄 Conversation reset")
    
    def interactive_mode(self):
        """Run in interactive mode"""
        print("\n🤖 E80 Troubleshooting Assistant (RAG - Responses API)")
        print("=" * 50)
        print("Ask questions about the E80 manual. Type 'exit' to quit.")
        print("Type 'reset' to start a new conversation.")
        print("=" * 50)
        
        while True:
            question = input("\n❓ Your question: ").strip()
            
            if question.lower() in ['exit', 'quit', 'q']:
                print("\n👋 Goodbye!")
                break
            
            if question.lower() == 'reset':
                self.reset_conversation()
                continue
            
            if not question:
                print("Please enter a question.")
                continue
            
            response = self.query(question)
            print("\n💡 Answer:")
            print("-" * 50)
            print(response)
            print("-" * 50)
    
    def batch_query(self, questions):
        """Process multiple questions"""
        results = []
        for i, question in enumerate(questions, 1):
            print(f"\n📌 Question {i}/{len(questions)}: {question}")
            response = self.query(question)
            results.append({
                "question": question,
                "answer": response
            })
            print(f"✅ Processed")
        
        return results


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Query the E80 manual using RAG")
    parser.add_argument("-q", "--question", type=str, help="Single question to ask")
    parser.add_argument("-i", "--interactive", action="store_true", 
                       help="Run in interactive mode")
    parser.add_argument("-f", "--file", type=str, 
                       help="File containing questions (one per line)")
    
    args = parser.parse_args()
    
    rag = RAGQuery()
    
    if args.question:
        # Single question mode
        print(f"\n❓ Question: {args.question}")
        response = rag.query(args.question)
        print("\n💡 Answer:")
        print("-" * 50)
        print(response)
        
    elif args.file:
        # Batch mode from file
        if not Path(args.file).exists():
            print(f"❌ File not found: {args.file}")
            sys.exit(1)
        
        with open(args.file, 'r') as f:
            questions = [line.strip() for line in f if line.strip()]
        
        print(f"\n📋 Processing {len(questions)} questions from {args.file}")
        results = rag.batch_query(questions)
        
        # Save results
        output_file = Path(args.file).stem + "_answers.json"
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n✅ Results saved to: {output_file}")
        
    else:
        # Interactive mode (default)
        rag.interactive_mode()


if __name__ == "__main__":
    main()
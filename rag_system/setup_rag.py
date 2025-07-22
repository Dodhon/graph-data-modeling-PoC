#!/usr/bin/env python3
"""
Setup script for OpenAI RAG system with E80 manual using Responses API
Creates vector store and uploads the manual for file search using the new Responses API
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import json
from datetime import datetime

# Load environment variables
load_dotenv()

class RAGSetup:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("❌ OPENAI_API_KEY not found in .env file")
            sys.exit(1)
        
        self.client = OpenAI(api_key=api_key)
        self.manual_path = Path(__file__).parent.parent / "data" / "input" / "E80_manual_text.txt"
        
    def create_vector_store(self, name="E80 Troubleshooting Manual"):
        """Create a new vector store for the manual with optimized chunking"""
        try:
            vector_store = self.client.vector_stores.create(
                name=name,
                chunking_strategy={
                    "type": "static",
                    "static": {
                        "max_chunk_size_tokens": 1600,
                        "chunk_overlap_tokens": 400
                    }
                },
                metadata={
                    "created_at": datetime.now().isoformat(),
                    "source": "E80 manual",
                    "type": "troubleshooting_documentation"
                }
            )
            print(f"✅ Created vector store: {vector_store.name} (ID: {vector_store.id})")
            return vector_store
        except Exception as e:
            print(f"❌ Error creating vector store: {e}")
            raise
    
    def upload_manual(self, vector_store_id):
        """Upload the E80 manual to the vector store"""
        if not self.manual_path.exists():
            print(f"❌ Manual not found at: {self.manual_path}")
            return None
        
        try:
            print(f"📄 Uploading manual from: {self.manual_path}")
            
            # First upload the file (purpose changed from "assistants" to "file_search")
            with open(self.manual_path, 'rb') as file:
                file_response = self.client.files.create(
                    file=file,
                    purpose="file_search"
                )
            
            print(f"📤 File uploaded (ID: {file_response.id})")
            
            # Then add it to the vector store
            vector_store_file = self.client.vector_stores.files.create(
                vector_store_id=vector_store_id,
                file_id=file_response.id
            )
            
            print(f"✅ File added to vector store")
            return file_response.id
            
        except Exception as e:
            print(f"❌ Error uploading manual: {e}")
            raise
    
    def validate_setup(self, vector_store_id):
        """Validate the setup by testing file search functionality"""
        try:
            # Test query using Responses API
            test_response = self.client.responses.create(
                model="gpt-4o",
                input="What is the main purpose of this E80 manual?",
                tools=[{
                    "type": "file_search",
                    "vector_store_ids": [vector_store_id]
                }]
            )
            
            print(f"✅ Vector store validation successful")
            print(f"📋 Test response: {test_response.choices[0].message.content[:100]}...")
            return True
        except Exception as e:
            print(f"❌ Error validating setup: {e}")
            return False
    
    def save_config(self, vector_store_id, file_id):
        """Save configuration for future use with Responses API"""
        config = {
            "vector_store_id": vector_store_id,
            "file_id": file_id,
            "api_type": "responses",
            "model": "gpt-4o",
            "created_at": datetime.now().isoformat(),
            "manual_path": str(self.manual_path)
        }
        
        config_path = Path(__file__).parent / "rag_config.json"
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"💾 Configuration saved to: {config_path}")
        return config_path
    
    def setup(self):
        """Run the complete setup process using Responses API"""
        print("🚀 Starting OpenAI RAG Setup for E80 Manual (Responses API)")
        print("-" * 50)
        
        # Create vector store
        vector_store = self.create_vector_store()
        
        # Upload manual
        file_id = self.upload_manual(vector_store.id)
        
        if file_id:
            # Validate setup
            if self.validate_setup(vector_store.id):
                # Save configuration
                self.save_config(vector_store.id, file_id)
                
                print("\n✅ RAG Setup Complete!")
                print(f"📊 Vector Store ID: {vector_store.id}")
                print(f"📄 File ID: {file_id}")
                print(f"🔧 API Type: Responses API")
                print("\nYou can now use query_rag.py to ask questions about the E80 manual.")
            else:
                print("\n❌ Setup validation failed")
        else:
            print("\n❌ Setup failed - manual upload unsuccessful")


if __name__ == "__main__":
    setup = RAGSetup()
    setup.setup()
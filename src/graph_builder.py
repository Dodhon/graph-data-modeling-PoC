"""
Knowledge Graph Builder for E80 Manual Processing
Combines LangChain's LLMGraphTransformer with AutoSchemaKG-inspired schema induction
"""

from typing import List, Dict, Any, Optional
import os
import time
from langchain.schema import Document
from langchain_experimental.graph_transformers import LLMGraphTransformer
from langchain_anthropic import ChatAnthropic
from langchain_community.graphs import Neo4jGraph
import re
import json


class ManualGraphBuilder:
    def __init__(self, anthropic_api_key: str, neo4j_uri: str = None, neo4j_username: str = None, neo4j_password: str = None):
        """Initialize the graph builder with LLM and optional Neo4j connection"""
        self.llm = ChatAnthropic(
            api_key=anthropic_api_key,
            model="claude-3-5-sonnet-20241022",
            temperature=0,
            timeout=90,
            max_retries=3,
            max_tokens=8192
        )
        
        # Initialize graph transformer for open discovery (no constraints)
        self.graph_transformer = LLMGraphTransformer(
            llm=self.llm,
            node_properties=True,  # Enable autonomous property extraction
            relationship_properties=True  # Enable relationship property extraction
        )
        
        # Initialize Neo4j if credentials provided
        self.graph_db = None
        if all([neo4j_uri, neo4j_username, neo4j_password]):
            try:
                self.graph_db = Neo4jGraph(
                    url=neo4j_uri,
                    username=neo4j_username,
                    password=neo4j_password
                )
            except Exception as e:
                print(f"Neo4j connection failed: {e}")
    
    def chunk_document(self, text: str, chunk_size: int = 800, overlap: int = 100) -> List[str]:
        """Split document into overlapping chunks for processing"""
        chunks = []
        for i in range(0, len(text), chunk_size - overlap):
            chunk = text[i:i + chunk_size]
            if chunk.strip():
                chunks.append(chunk)
        return chunks
    
    def preprocess_manual_text(self, text: str) -> str:
        """Clean and preprocess the manual text"""
        # Remove page markers
        text = re.sub(r'--- Page \d+ ---', '', text)
        # Remove line numbers at start
        text = re.sub(r'^\s*\d+→', '', text, flags=re.MULTILINE)
        # Clean up excessive whitespace
        text = re.sub(r'\n\s*\n', '\n', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def extract_graph_from_chunks(self, chunks: List[str], save_every: int = 100) -> List[Any]:
        """Extract graph documents from text chunks with periodic saving"""
        all_graph_docs = []
        
        for i, chunk in enumerate(chunks):
            print(f"Processing chunk {i+1}/{len(chunks)}")
            try:
                documents = [Document(page_content=chunk, metadata={"chunk_id": i})]
                graph_docs = self.graph_transformer.convert_to_graph_documents(documents)
                all_graph_docs.extend(graph_docs)
                
                # Update graph database after every chunk
                if self.graph_db and graph_docs:
                    try:
                        self.graph_db.add_graph_documents(graph_docs)
                        print(f"  Updated graph database with chunk {i+1}")
                    except Exception as e:
                        print(f"  Error updating graph database: {e}")
                
                # Periodic saving
                if (i + 1) % save_every == 0:
                    self._save_progress(all_graph_docs, i + 1, len(chunks))
                
                # Add small delay to avoid rate limiting
                if i % 20 == 0 and i > 0:
                    print("  Pausing to avoid rate limits...")
                    time.sleep(3)
                    
            except Exception as e:
                print(f"Error processing chunk {i}: {e}")
                # On connection error, wait longer before retrying
                if "connection" in str(e).lower():
                    print("  Waiting 10 seconds due to connection error...")
                    time.sleep(10)
                continue
        
        # Final save
        self._save_progress(all_graph_docs, len(chunks), len(chunks), final=True)
        
        return all_graph_docs
    
    def build_graph_from_manual_range(self, file_path: str, start_line: int = 0, end_line: int = None) -> Dict[str, Any]:
        """Build knowledge graph from a specific range of lines in the manual"""
        print(f"Reading manual file lines {start_line}-{end_line or 'end'}...")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Extract the specified range
        if end_line is None:
            end_line = len(lines)
        
        if start_line >= len(lines):
            raise ValueError(f"Start line {start_line} is beyond file length {len(lines)}")
        
        end_line = min(end_line, len(lines))
        selected_lines = lines[start_line:end_line]
        text = ''.join(selected_lines)
        
        lines_processed = len(selected_lines)
        print(f"Processing {lines_processed} lines ({start_line}-{end_line})")
        
        print("Preprocessing text...")
        clean_text = self.preprocess_manual_text(text)
        
        print("Chunking document...")
        chunks = self.chunk_document(clean_text)
        print(f"Created {len(chunks)} chunks")
        
        print("Extracting graph elements...")
        graph_docs = self.extract_graph_from_chunks(chunks)
        
        # Graph already stored incrementally during processing
        
        # Return summary statistics
        total_nodes = sum(len(doc.nodes) for doc in graph_docs)
        total_relationships = sum(len(doc.relationships) for doc in graph_docs)
        
        return {
            "lines_processed": lines_processed,
            "start_line": start_line,
            "end_line": end_line,
            "total_chunks": len(chunks),
            "total_graph_documents": len(graph_docs),
            "total_nodes": total_nodes,
            "total_relationships": total_relationships,
            "graph_documents": graph_docs
        }
    
    def _save_progress(self, graph_docs: List[Any], processed: int, total: int, final: bool = False):
        """Save progress to JSON file"""
        if final:
            filename = "e80_knowledge_graph_final.json"
            print(f"💾 Saving final results to {filename}")
        else:
            filename = f"e80_knowledge_graph_progress_{processed}of{total}.json"
            print(f"💾 Saving progress: {processed}/{total} chunks to {filename}")
        
        try:
            self.export_graph_json(graph_docs, filename)
            
            # Also save summary stats
            total_nodes = sum(len(doc.nodes) for doc in graph_docs)
            total_relationships = sum(len(doc.relationships) for doc in graph_docs)
            
            stats = {
                "processed_chunks": processed,
                "total_chunks": total,
                "progress_percentage": round((processed / total) * 100, 1),
                "total_nodes": total_nodes,
                "total_relationships": total_relationships,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            
            stats_filename = filename.replace('.json', '_stats.json')
            with open(stats_filename, 'w') as f:
                json.dump(stats, f, indent=2)
                
        except Exception as e:
            print(f"  ⚠️  Error saving progress: {e}")
    
    def build_graph_from_manual(self, file_path: str, max_lines: int = None) -> Dict[str, Any]:
        """Main method to build knowledge graph from manual"""
        print("Reading manual file...")
        with open(file_path, 'r', encoding='utf-8') as f:
            if max_lines:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        break
                    lines.append(line)
                text = ''.join(lines)
                print(f"Limited to first {max_lines} lines")
            else:
                text = f.read()
        
        print("Preprocessing text...")
        clean_text = self.preprocess_manual_text(text)
        
        print("Chunking document...")
        chunks = self.chunk_document(clean_text)
        print(f"Created {len(chunks)} chunks")
        
        print("Extracting graph elements...")
        graph_docs = self.extract_graph_from_chunks(chunks)
        
        # Graph already stored incrementally during processing
        
        # Return summary statistics
        total_nodes = sum(len(doc.nodes) for doc in graph_docs)
        total_relationships = sum(len(doc.relationships) for doc in graph_docs)
        
        return {
            "total_chunks": len(chunks),
            "total_graph_documents": len(graph_docs),
            "total_nodes": total_nodes,
            "total_relationships": total_relationships,
            "graph_documents": graph_docs
        }
    
    def export_graph_json(self, graph_docs: List[Any], output_path: str):
        """Export graph data to JSON format"""
        export_data = {
            "nodes": [],
            "relationships": []
        }
        
        for doc in graph_docs:
            for node in doc.nodes:
                export_data["nodes"].append({
                    "id": node.id,
                    "type": node.type,
                    "properties": node.properties
                })
            
            for rel in doc.relationships:
                export_data["relationships"].append({
                    "source": rel.source.id,
                    "target": rel.target.id,
                    "type": rel.type,
                    "properties": rel.properties
                })
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        print(f"Graph exported to {output_path}")


if __name__ == "__main__":
    # Example usage
    from dotenv import load_dotenv
    load_dotenv()
    
    builder = ManualGraphBuilder(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        neo4j_uri=os.getenv("NEO4J_URI"),
        neo4j_username=os.getenv("NEO4J_USERNAME"),
        neo4j_password=os.getenv("NEO4J_PASSWORD")
    )
    
    result = builder.build_graph_from_manual("E80_manual_text.txt")
    print(f"Graph construction complete: {result}")
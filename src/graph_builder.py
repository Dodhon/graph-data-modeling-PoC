"""
Knowledge Graph Builder for E80 Manual Processing
Uses Entity-Event-Concept extraction for troubleshooting-optimized knowledge graphs
"""

from typing import List, Dict, Any, Optional
import os
import time
from langchain.schema import Document
from langchain_anthropic import ChatAnthropic
from langchain_community.graphs import Neo4jGraph
import re
import json
from .eec_graph_transformer import EECGraphTransformer, EECGraphDocument
from .temporal_extractor import TemporalExtractor
from .schema_inducer import SchemaInducer


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
        
        # Initialize EEC graph transformer for troubleshooting-optimized extraction
        self.eec_transformer = EECGraphTransformer(llm=self.llm)
        
        # Initialize temporal extractor for sequence and causal analysis
        self.temporal_extractor = TemporalExtractor(llm=self.llm)
        
        # Initialize schema inducer for hierarchical organization
        self.schema_inducer = SchemaInducer(llm=self.llm)
        
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
    
    def extract_graph_from_chunks(self, chunks: List[str], save_every: int = 100, start_chunk: int = 0) -> List[EECGraphDocument]:
        """Extract EEC graph documents from text chunks with periodic saving
        
        Args:
            chunks: List of text chunks to process
            save_every: Save progress every N chunks
            start_chunk: Starting chunk index (default: 0)
        """
        all_eec_docs = []
        
        # Validate start_chunk
        if start_chunk < 0:
            raise ValueError(f"start_chunk must be non-negative, got {start_chunk}")
        if start_chunk >= len(chunks):
            raise ValueError(f"start_chunk {start_chunk} is beyond total chunks {len(chunks)}")
        
        if start_chunk > 0:
            print(f"⚡ Skipping first {start_chunk} chunks, starting from chunk {start_chunk+1}")
        
        for i in range(start_chunk, len(chunks)):
            chunk = chunks[i]
            print(f"Processing chunk {i+1}/{len(chunks)}")
            try:
                documents = [Document(page_content=chunk, metadata={"chunk_id": i, "source": "manual"})]
                eec_docs = self.eec_transformer.convert_to_eec_documents(documents)
                all_eec_docs.extend(eec_docs)
                
                # Update graph database after every chunk
                if self.graph_db and eec_docs:
                    try:
                        self._update_neo4j_with_eec(eec_docs)
                        print(f"  Updated graph database with chunk {i+1}")
                    except Exception as e:
                        print(f"  Error updating graph database: {e}")
                
                # Periodic saving
                if (i + 1) % save_every == 0:
                    self._save_eec_progress(all_eec_docs, i + 1, len(chunks))
                
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
        self._save_eec_progress(all_eec_docs, len(chunks), len(chunks), final=True)
        
        return all_eec_docs
    
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
    
    def _update_neo4j_with_eec(self, eec_docs: List[EECGraphDocument]):
        """Update Neo4j database with EEC documents"""
        for doc in eec_docs:
            # Add entities
            for entity in doc.entities:
                # Filter out empty dictionaries and None values
                properties = {k: v for k, v in entity.properties.items() if v is not None and v != {}}
                concepts = entity.concepts if entity.concepts else []
                
                query = f"""
                MERGE (e:Entity:{entity.type} {{id: $id}})
                SET e += $properties
                SET e.concepts = $concepts
                SET e.source_chunk = $source_chunk
                """
                self.graph_db.query(query, {
                    "id": entity.id,
                    "properties": properties,
                    "concepts": concepts,
                    "source_chunk": entity.source_chunk
                })
            
            # Add events
            for event in doc.events:
                # Filter out empty dictionaries and None values
                properties = {k: v for k, v in event.properties.items() if v is not None and v != {}}
                prerequisites = event.prerequisites if event.prerequisites else []
                concepts = event.concepts if event.concepts else []
                
                query = f"""
                MERGE (e:Event:{event.type} {{id: $id}})
                SET e += $properties
                SET e.actor = $actor
                SET e.target = $target
                SET e.temporal_order = $temporal_order
                SET e.prerequisites = $prerequisites
                SET e.concepts = $concepts
                SET e.source_chunk = $source_chunk
                """
                self.graph_db.query(query, {
                    "id": event.id,
                    "properties": properties,
                    "actor": event.actor,
                    "target": event.target,
                    "temporal_order": event.temporal_order,
                    "prerequisites": prerequisites,
                    "concepts": concepts,
                    "source_chunk": event.source_chunk
                })
            
            # Add concepts
            for concept in doc.concepts:
                # Filter out empty dictionaries and None values
                properties = {k: v for k, v in concept.properties.items() if v is not None and v != {}}
                applies_to = concept.applies_to if concept.applies_to else []
                
                query = f"""
                MERGE (c:Concept:{concept.type} {{id: $id}})
                SET c += $properties
                SET c.applies_to = $applies_to
                SET c.domain = $domain
                SET c.source_chunk = $source_chunk
                """
                self.graph_db.query(query, {
                    "id": concept.id,
                    "properties": properties,
                    "applies_to": applies_to,
                    "domain": concept.domain,
                    "source_chunk": concept.source_chunk
                })
            
            # Add relationships
            for relationship in doc.relationships:
                # Filter out empty dictionaries and None values
                properties = {k: v for k, v in relationship.properties.items() if v is not None and v != {}}
                
                # Only set temporal_info if it contains actual data
                if relationship.temporal_info and any(v for v in relationship.temporal_info.values()):
                    query = f"""
                    MATCH (a {{id: $source}})
                    MATCH (b {{id: $target}})
                    MERGE (a)-[r:{relationship.type}]->(b)
                    SET r += $properties
                    SET r.temporal_info = $temporal_info
                    """
                    params = {
                        "source": relationship.source,
                        "target": relationship.target,
                        "properties": properties,
                        "temporal_info": relationship.temporal_info
                    }
                else:
                    query = f"""
                    MATCH (a {{id: $source}})
                    MATCH (b {{id: $target}})
                    MERGE (a)-[r:{relationship.type}]->(b)
                    SET r += $properties
                    """
                    params = {
                        "source": relationship.source,
                        "target": relationship.target,
                        "properties": properties
                    }
                
                self.graph_db.query(query, params)
    
    def _save_eec_progress(self, eec_docs: List[EECGraphDocument], processed: int, total: int, final: bool = False):
        """Save EEC progress to JSON file"""
        if final:
            filename = "e80_eec_knowledge_graph_final.json"
            print(f"💾 Saving final EEC results to {filename}")
        else:
            filename = f"e80_eec_knowledge_graph_progress_{processed}of{total}.json"
            print(f"💾 Saving EEC progress: {processed}/{total} chunks to {filename}")
        
        try:
            self.export_eec_json(eec_docs, filename)
            
            # Calculate EEC stats
            total_entities = sum(len(doc.entities) for doc in eec_docs)
            total_events = sum(len(doc.events) for doc in eec_docs)
            total_concepts = sum(len(doc.concepts) for doc in eec_docs)
            total_relationships = sum(len(doc.relationships) for doc in eec_docs)
            
            stats = {
                "processed_chunks": processed,
                "total_chunks": total,
                "progress_percentage": round((processed / total) * 100, 1),
                "total_entities": total_entities,
                "total_events": total_events,
                "total_concepts": total_concepts,
                "total_relationships": total_relationships,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            
            stats_filename = filename.replace('.json', '_stats.json')
            with open(stats_filename, 'w') as f:
                json.dump(stats, f, indent=2)
                
        except Exception as e:
            print(f"  ⚠️  Error saving EEC progress: {e}")
    
    def export_eec_json(self, eec_docs: List[EECGraphDocument], output_path: str):
        """Export EEC data to JSON format"""
        export_data = {
            "entities": [],
            "events": [],
            "concepts": [],
            "relationships": []
        }
        
        for doc in eec_docs:
            # Add entities
            for entity in doc.entities:
                export_data["entities"].append({
                    "id": entity.id,
                    "type": entity.type,
                    "properties": entity.properties,
                    "concepts": entity.concepts,
                    "source_chunk": entity.source_chunk
                })
            
            # Add events
            for event in doc.events:
                export_data["events"].append({
                    "id": event.id,
                    "type": event.type,
                    "properties": event.properties,
                    "actor": event.actor,
                    "target": event.target,
                    "temporal_order": event.temporal_order,
                    "prerequisites": event.prerequisites,
                    "concepts": event.concepts,
                    "source_chunk": event.source_chunk
                })
            
            # Add concepts
            for concept in doc.concepts:
                export_data["concepts"].append({
                    "id": concept.id,
                    "type": concept.type,
                    "properties": concept.properties,
                    "applies_to": concept.applies_to,
                    "domain": concept.domain,
                    "source_chunk": concept.source_chunk
                })
            
            # Add relationships
            for relationship in doc.relationships:
                export_data["relationships"].append({
                    "source": relationship.source,
                    "target": relationship.target,
                    "type": relationship.type,
                    "properties": relationship.properties,
                    "temporal_info": relationship.temporal_info
                })
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        print(f"EEC graph exported to {output_path}")

    def process_temporal_and_schema(self, eec_docs: List[EECGraphDocument]) -> Dict[str, Any]:
        """Process temporal patterns and induce schemas from EEC documents"""
        
        print("Extracting temporal patterns...")
        temporal_patterns = self.temporal_extractor.extract_temporal_patterns(eec_docs)
        
        print("Inducing schemas...")
        schemas = self.schema_inducer.induce_schemas(eec_docs)
        
        # Export temporal patterns and schemas
        self.temporal_extractor.export_temporal_patterns(temporal_patterns, "e80_temporal_patterns.json")
        self.schema_inducer.export_schemas(schemas, "e80_schemas.json")
        
        return {
            "temporal_patterns": temporal_patterns,
            "schemas": schemas
        }

    def build_graph_from_manual(self, file_path: str, max_lines: int = None, start_chunk: int = 0) -> Dict[str, Any]:
        """Main method to build knowledge graph from manual
        
        Args:
            file_path: Path to the manual text file
            max_lines: Optional limit on number of lines to process
            start_chunk: Starting chunk index (default: 0)
        """
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
        
        # Validate start_chunk parameter
        if start_chunk < 0:
            raise ValueError(f"start_chunk must be non-negative, got {start_chunk}")
        if start_chunk >= len(chunks):
            print(f"⚠️  Warning: start_chunk {start_chunk} >= total chunks {len(chunks)}")
            print("Nothing to process.")
            return {
                "total_chunks": len(chunks),
                "total_eec_documents": 0,
                "total_entities": 0,
                "total_events": 0,
                "total_concepts": 0,
                "total_relationships": 0,
                "eec_documents": [],
                "temporal_patterns": {"diagnostic_sequences": [], "causal_chains": [], 
                                    "prerequisite_graphs": [], "conditional_logic": []},
                "schemas": {"entity_hierarchies": [], "event_patterns": [], 
                           "concept_networks": [], "domain_schemas": []}
            }
        
        print("Extracting EEC graph elements...")
        eec_docs = self.extract_graph_from_chunks(chunks, start_chunk=start_chunk)
        
        # Graph already stored incrementally during processing
        
        # Process temporal patterns and schemas
        temporal_and_schema = self.process_temporal_and_schema(eec_docs)
        
        # Return EEC summary statistics
        total_entities = sum(len(doc.entities) for doc in eec_docs)
        total_events = sum(len(doc.events) for doc in eec_docs)
        total_concepts = sum(len(doc.concepts) for doc in eec_docs)
        total_relationships = sum(len(doc.relationships) for doc in eec_docs)
        
        return {
            "total_chunks": len(chunks),
            "total_eec_documents": len(eec_docs),
            "total_entities": total_entities,
            "total_events": total_events,
            "total_concepts": total_concepts,
            "total_relationships": total_relationships,
            "eec_documents": eec_docs,
            "temporal_patterns": temporal_and_schema["temporal_patterns"],
            "schemas": temporal_and_schema["schemas"]
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
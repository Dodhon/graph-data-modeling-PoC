"""
Entity-Event-Concept Graph Transformer for Technical Documentation
Specialized for troubleshooting LGV malfunctions and multi-domain fault resolution
"""

from typing import List, Dict, Any, Optional, Tuple
from langchain.schema import Document
from langchain_anthropic import ChatAnthropic
from dataclasses import dataclass
import json
import re
from datetime import datetime


@dataclass
class Entity:
    """Represents a concrete object, component, person, or location"""
    id: str
    type: str
    properties: Dict[str, Any]
    concepts: List[str] = None
    source_chunk: str = None
    
    def __post_init__(self):
        if self.concepts is None:
            self.concepts = []


@dataclass
class Event:
    """Represents an action, process, or procedure"""
    id: str
    type: str
    properties: Dict[str, Any]
    actor: str = None
    target: str = None
    temporal_order: int = None
    prerequisites: List[str] = None
    concepts: List[str] = None
    source_chunk: str = None
    
    def __post_init__(self):
        if self.prerequisites is None:
            self.prerequisites = []
        if self.concepts is None:
            self.concepts = []


@dataclass
class Concept:
    """Represents abstract ideas, principles, or categories"""
    id: str
    type: str
    properties: Dict[str, Any]
    applies_to: List[str] = None
    domain: str = None
    source_chunk: str = None
    
    def __post_init__(self):
        if self.applies_to is None:
            self.applies_to = []


@dataclass
class Relationship:
    """Represents connections between entities, events, or concepts"""
    source: str
    target: str
    type: str
    properties: Dict[str, Any]
    temporal_info: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.temporal_info is None:
            self.temporal_info = {}


@dataclass
class EECGraphDocument:
    """Container for extracted entities, events, concepts, and relationships"""
    entities: List[Entity]
    events: List[Event]
    concepts: List[Concept]
    relationships: List[Relationship]
    source_metadata: Dict[str, Any]


class EECGraphTransformer:
    """
    Transformer that extracts entities, events, and concepts from technical documentation
    Optimized for troubleshooting scenarios and multi-domain fault resolution
    """
    
    def __init__(self, llm: ChatAnthropic):
        self.llm = llm
        
    def convert_to_eec_documents(self, documents: List[Document]) -> List[EECGraphDocument]:
        """Convert documents to EEC graph format"""
        eec_documents = []
        
        for doc in documents:
            # Extract entities, events, and concepts
            entities = self._extract_entities(doc)
            events = self._extract_events(doc)
            concepts = self._extract_concepts(doc)
            relationships = self._extract_relationships(entities, events, concepts, doc)
            
            eec_doc = EECGraphDocument(
                entities=entities,
                events=events,
                concepts=concepts,
                relationships=relationships,
                source_metadata=doc.metadata
            )
            eec_documents.append(eec_doc)
            
        return eec_documents
    
    def _extract_entities(self, document: Document) -> List[Entity]:
        """Extract concrete entities (components, tools, people, locations)"""
        entity_prompt = f"""
        Extract concrete entities from this text. Focus on LGV troubleshooting.
        
        Categories: COMPONENTS, TOOLS, PEOPLE, LOCATIONS, SYMPTOMS, MEASUREMENTS
        
        Text: {document.page_content}
        
        IMPORTANT: Return ONLY valid JSON array. No explanations. If no entities found, return [].
        
        Format:
        [
            {{
                "id": "unique_entity_name",
                "type": "COMPONENT|TOOL|PERSON|LOCATION|SYMPTOM|MEASUREMENT",
                "properties": {{
                    "name": "display name",
                    "description": "brief description",
                    "domain": "hardware|software|environmental|human",
                    "criticality": "high|medium|low"
                }}
            }}
        ]
        """
        
        try:
            response = self.llm.invoke(entity_prompt)
            
            # Handle both string and object responses
            if hasattr(response, 'content'):
                content = response.content
            else:
                content = str(response)
                
            print(f"  Entity response: {content[:200]}...")
            
            # Clean response content
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            # Handle responses that don't contain JSON at all
            if '[' not in content and '{' not in content:
                print(f"  No JSON found in entity response, returning empty list")
                return []
            
            # Extract JSON from response if it contains extra text
            try:
                # Look for both array and object formats
                json_part = None
                
                # Try to find JSON array first
                if '[' in content:
                    start = content.find('[')
                    bracket_count = 0
                    end = start
                    for i, char in enumerate(content[start:], start):
                        if char == '[':
                            bracket_count += 1
                        elif char == ']':
                            bracket_count -= 1
                            if bracket_count == 0:
                                end = i + 1
                                break
                    json_part = content[start:end]
                
                # If no valid array found, try object format
                if not json_part and '{' in content:
                    start = content.find('{')
                    brace_count = 0
                    end = start
                    for i, char in enumerate(content[start:], start):
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                end = i + 1
                                break
                    json_part = content[start:end]
                
                if not json_part:
                    json_part = content
                
                parsed_data = json.loads(json_part)
                
                # Handle wrapped responses like {"entities": [...]}
                if isinstance(parsed_data, dict) and "entities" in parsed_data:
                    entities_data = parsed_data["entities"]
                else:
                    entities_data = parsed_data
                    
            except json.JSONDecodeError:
                print(f"  Could not parse JSON from entity response")
                return []
            
            entities = []
            for entity_data in entities_data:
                entity = Entity(
                    id=entity_data["id"],
                    type=entity_data["type"],
                    properties=entity_data["properties"],
                    source_chunk=document.page_content[:100] + "..."
                )
                entities.append(entity)
                
            return entities
            
        except Exception as e:
            print(f"Error extracting entities: {e}")
            print(f"Response was: {content if 'content' in locals() else 'Unable to get response'}")
            return []
    
    def _extract_events(self, document: Document) -> List[Event]:
        """Extract events (procedures, actions, processes)"""
        event_prompt = f"""
        Extract events/procedures from this text. Focus on LGV troubleshooting actions.
        
        Categories: DIAGNOSTIC, MAINTENANCE, SAFETY, OPERATIONAL, FAILURE
        
        Text: {document.page_content}
        
        IMPORTANT: Return ONLY valid JSON array. No explanations. If no events found, return [].
        
        Format:
        [
            {{
                "id": "unique_event_name",
                "type": "DIAGNOSTIC|MAINTENANCE|SAFETY|OPERATIONAL|FAILURE",
                "properties": {{
                    "name": "display name",
                    "description": "detailed description",
                    "frequency": "as_needed|daily|weekly|monthly|annual",
                    "duration": "estimated time",
                    "safety_level": "high|medium|low",
                    "domain": "hardware|software|environmental|human"
                }},
                "actor": "who performs this event",
                "target": "what this event affects",
                "temporal_order": "sequence number if part of procedure"
            }}
        ]
        """
        
        try:
            response = self.llm.invoke(event_prompt)
            
            # Handle both string and object responses
            if hasattr(response, 'content'):
                content = response.content
            else:
                content = str(response)
                
            print(f"  Event response: {content[:200]}...")
            
            # Clean response content
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            # Handle responses that don't contain JSON at all
            if '[' not in content and '{' not in content:
                print(f"  No JSON found in event response, returning empty list")
                return []
            
            # Extract JSON from response if it contains extra text
            try:
                # Look for both array and object formats
                json_part = None
                
                # Try to find JSON array first
                if '[' in content:
                    start = content.find('[')
                    bracket_count = 0
                    end = start
                    for i, char in enumerate(content[start:], start):
                        if char == '[':
                            bracket_count += 1
                        elif char == ']':
                            bracket_count -= 1
                            if bracket_count == 0:
                                end = i + 1
                                break
                    json_part = content[start:end]
                
                # If no valid array found, try object format
                if not json_part and '{' in content:
                    start = content.find('{')
                    brace_count = 0
                    end = start
                    for i, char in enumerate(content[start:], start):
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                end = i + 1
                                break
                    json_part = content[start:end]
                
                if not json_part:
                    json_part = content
                
                parsed_data = json.loads(json_part)
                
                # Handle wrapped responses
                if isinstance(parsed_data, dict) and "events" in parsed_data:
                    events_data = parsed_data["events"]
                else:
                    events_data = parsed_data
                    
            except json.JSONDecodeError:
                print(f"  Could not parse JSON from event response")
                return []
            
            events = []
            for event_data in events_data:
                event = Event(
                    id=event_data["id"],
                    type=event_data["type"],
                    properties=event_data["properties"],
                    actor=event_data.get("actor"),
                    target=event_data.get("target"),
                    temporal_order=event_data.get("temporal_order"),
                    source_chunk=document.page_content[:100] + "..."
                )
                events.append(event)
                
            return events
            
        except Exception as e:
            print(f"Error extracting events: {e}")
            print(f"Response was: {content if 'content' in locals() else 'Unable to get response'}")
            return []
    
    def _extract_concepts(self, document: Document) -> List[Concept]:
        """Extract abstract concepts (principles, categories, knowledge)"""
        concept_prompt = f"""
        Extract abstract concepts from this text. Focus on troubleshooting principles.
        
        Categories: SAFETY_PRINCIPLES, DIAGNOSTIC_LOGIC, MAINTENANCE_CONCEPTS, OPERATIONAL_PRINCIPLES, FAILURE_PATTERNS, TECHNICAL_CONCEPTS
        
        Text: {document.page_content}
        
        IMPORTANT: Return ONLY valid JSON array. No explanations. If no concepts found, return [].
        
        Format:
        [
            {{
                "id": "unique_concept_name",
                "type": "SAFETY_PRINCIPLES|DIAGNOSTIC_LOGIC|MAINTENANCE_CONCEPTS|OPERATIONAL_PRINCIPLES|FAILURE_PATTERNS|TECHNICAL_CONCEPTS",
                "properties": {{
                    "name": "display name",
                    "description": "detailed description",
                    "importance": "critical|high|medium|low",
                    "domain": "hardware|software|environmental|human"
                }},
                "domain": "specific technical domain"
            }}
        ]
        """
        
        try:
            response = self.llm.invoke(concept_prompt)
            
            # Handle both string and object responses
            if hasattr(response, 'content'):
                content = response.content
            else:
                content = str(response)
                
            print(f"  Concept response: {content[:200]}...")
            
            # Clean response content
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            # Handle responses that don't contain JSON at all
            if '[' not in content and '{' not in content:
                print(f"  No JSON found in concept response, returning empty list")
                return []
            
            # Extract JSON from response if it contains extra text
            try:
                # Look for both array and object formats
                json_part = None
                
                # Try to find JSON array first
                if '[' in content:
                    start = content.find('[')
                    bracket_count = 0
                    end = start
                    for i, char in enumerate(content[start:], start):
                        if char == '[':
                            bracket_count += 1
                        elif char == ']':
                            bracket_count -= 1
                            if bracket_count == 0:
                                end = i + 1
                                break
                    json_part = content[start:end]
                
                # If no valid array found, try object format
                if not json_part and '{' in content:
                    start = content.find('{')
                    brace_count = 0
                    end = start
                    for i, char in enumerate(content[start:], start):
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                end = i + 1
                                break
                    json_part = content[start:end]
                
                if not json_part:
                    json_part = content
                
                parsed_data = json.loads(json_part)
                
                # Handle wrapped responses
                if isinstance(parsed_data, dict) and "concepts" in parsed_data:
                    concepts_data = parsed_data["concepts"]
                else:
                    concepts_data = parsed_data
                    
            except json.JSONDecodeError:
                print(f"  Could not parse JSON from concept response")
                return []
            
            concepts = []
            for concept_data in concepts_data:
                concept = Concept(
                    id=concept_data["id"],
                    type=concept_data["type"],
                    properties=concept_data["properties"],
                    domain=concept_data.get("domain"),
                    source_chunk=document.page_content[:100] + "..."
                )
                concepts.append(concept)
                
            return concepts
            
        except Exception as e:
            print(f"Error extracting concepts: {e}")
            print(f"Response was: {content if 'content' in locals() else 'Unable to get response'}")
            return []
    
    def _extract_relationships(self, entities: List[Entity], events: List[Event], 
                             concepts: List[Concept], document: Document) -> List[Relationship]:
        """Extract relationships between entities, events, and concepts"""
        
        # Create lookup for all extracted items
        all_items = {item.id: item for item in entities + events + concepts}
        
        relationship_prompt = f"""
        Identify relationships between these items for LGV troubleshooting.
        
        Entities: {[{"id": e.id, "type": e.type} for e in entities]}
        Events: {[{"id": e.id, "type": e.type} for e in events]}
        Concepts: {[{"id": c.id, "type": c.type} for c in concepts]}
        
        Relationship types: CAUSES, REQUIRES, PREVENTS, DIAGNOSES, FIXES, APPLIES_TO, PART_OF, HAPPENS_BEFORE, TRIGGERS
        
        Text: {document.page_content}
        
        IMPORTANT: Return ONLY valid JSON array. No explanations. If no relationships found, return [].
        
        Format:
        [
            {{
                "source": "source_id",
                "target": "target_id", 
                "type": "relationship_type",
                "properties": {{
                    "context": "description of relationship",
                    "confidence": "high|medium|low",
                    "domain": "hardware|software|environmental|human"
                }}
            }}
        ]
        """
        
        try:
            response = self.llm.invoke(relationship_prompt)
            
            # Handle both string and object responses
            if hasattr(response, 'content'):
                content = response.content
            else:
                content = str(response)
                
            print(f"  Relationship response: {content[:200]}...")
            
            # Clean response content
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            # Handle responses that don't contain JSON at all
            if '[' not in content and '{' not in content:
                print(f"  No JSON found in relationship response, returning empty list")
                return []
            
            # Extract JSON from response if it contains extra text
            try:
                # Look for both array and object formats
                json_part = None
                
                # Try to find JSON array first
                if '[' in content:
                    start = content.find('[')
                    bracket_count = 0
                    end = start
                    for i, char in enumerate(content[start:], start):
                        if char == '[':
                            bracket_count += 1
                        elif char == ']':
                            bracket_count -= 1
                            if bracket_count == 0:
                                end = i + 1
                                break
                    json_part = content[start:end]
                
                # If no valid array found, try object format
                if not json_part and '{' in content:
                    start = content.find('{')
                    brace_count = 0
                    end = start
                    for i, char in enumerate(content[start:], start):
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                end = i + 1
                                break
                    json_part = content[start:end]
                
                if not json_part:
                    json_part = content
                
                parsed_data = json.loads(json_part)
                
                # Handle wrapped responses
                if isinstance(parsed_data, dict) and "relationships" in parsed_data:
                    relationships_data = parsed_data["relationships"]
                else:
                    relationships_data = parsed_data
                    
            except json.JSONDecodeError:
                print(f"  Could not parse JSON from relationship response")
                return []
            
            relationships = []
            for rel_data in relationships_data:
                # Validate that source and target exist
                if (rel_data["source"] in all_items and 
                    rel_data["target"] in all_items):
                    
                    relationship = Relationship(
                        source=rel_data["source"],
                        target=rel_data["target"],
                        type=rel_data["type"],
                        properties=rel_data["properties"]
                    )
                    relationships.append(relationship)
                    
            return relationships
            
        except Exception as e:
            print(f"Error extracting relationships: {e}")
            print(f"Response was: {content if 'content' in locals() else 'Unable to get response'}")
            return []
    
    def export_to_neo4j_format(self, eec_documents: List[EECGraphDocument]) -> Dict[str, Any]:
        """Convert EEC documents to Neo4j-compatible format"""
        neo4j_data = {
            "nodes": [],
            "relationships": []
        }
        
        for doc in eec_documents:
            # Add entities as nodes
            for entity in doc.entities:
                neo4j_data["nodes"].append({
                    "id": entity.id,
                    "labels": ["Entity", entity.type],
                    "properties": {
                        **entity.properties,
                        "node_type": "entity",
                        "concepts": entity.concepts,
                        "source_chunk": entity.source_chunk
                    }
                })
            
            # Add events as nodes
            for event in doc.events:
                neo4j_data["nodes"].append({
                    "id": event.id,
                    "labels": ["Event", event.type],
                    "properties": {
                        **event.properties,
                        "node_type": "event",
                        "actor": event.actor,
                        "target": event.target,
                        "temporal_order": event.temporal_order,
                        "prerequisites": event.prerequisites,
                        "concepts": event.concepts,
                        "source_chunk": event.source_chunk
                    }
                })
            
            # Add concepts as nodes
            for concept in doc.concepts:
                neo4j_data["nodes"].append({
                    "id": concept.id,
                    "labels": ["Concept", concept.type],
                    "properties": {
                        **concept.properties,
                        "node_type": "concept",
                        "applies_to": concept.applies_to,
                        "domain": concept.domain,
                        "source_chunk": concept.source_chunk
                    }
                })
            
            # Add relationships
            for relationship in doc.relationships:
                neo4j_data["relationships"].append({
                    "source": relationship.source,
                    "target": relationship.target,
                    "type": relationship.type,
                    "properties": {
                        **relationship.properties,
                        "temporal_info": relationship.temporal_info
                    }
                })
        
        return neo4j_data
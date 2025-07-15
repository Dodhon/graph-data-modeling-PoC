"""
Schema Inducer for Knowledge Graph Construction
Creates hierarchical schemas and concept networks from extracted EEC data
Inspired by AutoSchemaKG methodology
"""

from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
from collections import defaultdict
from langchain_anthropic import ChatAnthropic
from .eec_graph_transformer import Entity, Event, Concept, EECGraphDocument
import json


@dataclass
class EntityHierarchy:
    """Represents hierarchical organization of entities"""
    root_concept: str
    hierarchy: Dict[str, List[str]]
    instances: Dict[str, List[str]]
    domain: str


@dataclass
class EventPattern:
    """Represents patterns in event sequences"""
    pattern_id: str
    pattern_type: str
    events: List[str]
    frequency: int
    domain: str
    context: str


@dataclass
class ConceptNetwork:
    """Represents relationships between concepts"""
    concept_id: str
    related_concepts: List[str]
    relationship_types: List[str]
    domain: str
    abstraction_level: int


@dataclass
class DomainSchema:
    """Represents complete schema for a domain"""
    domain_name: str
    entity_types: List[str]
    event_types: List[str]
    concept_types: List[str]
    relationship_patterns: List[str]
    key_principles: List[str]


class SchemaInducer:
    """
    Induces hierarchical schemas from EEC documents
    Creates concept networks and domain-specific taxonomies
    """
    
    def __init__(self, llm: ChatAnthropic):
        self.llm = llm
    
    def induce_schemas(self, eec_docs: List[EECGraphDocument]) -> Dict[str, Any]:
        """Main method to induce all schema types from EEC documents"""
        
        # Collect all entities, events, and concepts
        all_entities = []
        all_events = []
        all_concepts = []
        
        for doc in eec_docs:
            all_entities.extend(doc.entities)
            all_events.extend(doc.events)
            all_concepts.extend(doc.concepts)
        
        # Generate different types of schemas
        entity_hierarchies = self.create_entity_hierarchies(all_entities)
        event_patterns = self.identify_event_patterns(all_events)
        concept_networks = self.build_concept_networks(all_concepts)
        domain_schemas = self.generate_domain_schemas(all_entities, all_events, all_concepts)
        
        return {
            "entity_hierarchies": entity_hierarchies,
            "event_patterns": event_patterns,
            "concept_networks": concept_networks,
            "domain_schemas": domain_schemas
        }
    
    def create_entity_hierarchies(self, entities: List[Entity]) -> List[EntityHierarchy]:
        """Create hierarchical organization of entities"""
        
        # Group entities by domain and type
        entity_groups = defaultdict(list)
        for entity in entities:
            domain = entity.properties.get("domain", "unknown")
            entity_groups[domain].append(entity)
        
        hierarchies = []
        
        for domain, domain_entities in entity_groups.items():
            # Group by entity type
            type_groups = defaultdict(list)
            for entity in domain_entities:
                type_groups[entity.type].append(entity)
            
            # Create hierarchy for each type
            for entity_type, type_entities in type_groups.items():
                
                entity_info = []
                for entity in type_entities:
                    entity_info.append({
                        "id": entity.id,
                        "name": entity.properties.get("name", entity.id),
                        "description": entity.properties.get("description", ""),
                        "properties": entity.properties
                    })
                
                hierarchy_prompt = f"""
                Create a hierarchical organization of these {entity_type} entities from the {domain} domain.
                Focus on creating a taxonomy that supports troubleshooting and maintenance.
                
                Entities: {json.dumps(entity_info, indent=2)}
                
                Create a hierarchy that shows:
                1. Abstract categories (top level)
                2. Specific subcategories (middle level)
                3. Concrete instances (bottom level)
                
                Return a JSON object:
                {{
                    "root_concept": "top_level_category_name",
                    "hierarchy": {{
                        "abstract_category": ["subcategory1", "subcategory2"],
                        "subcategory1": ["specific_type1", "specific_type2"]
                    }},
                    "instances": {{
                        "specific_type1": ["entity_id1", "entity_id2"]
                    }},
                    "domain": "{domain}"
                }}
                """
                
                try:
                    response = self.llm.invoke(hierarchy_prompt)
                    hierarchy_data = json.loads(response.content)
                    
                    hierarchy = EntityHierarchy(
                        root_concept=hierarchy_data["root_concept"],
                        hierarchy=hierarchy_data["hierarchy"],
                        instances=hierarchy_data["instances"],
                        domain=hierarchy_data["domain"]
                    )
                    hierarchies.append(hierarchy)
                    
                except Exception as e:
                    print(f"Error creating hierarchy for {entity_type} in {domain}: {e}")
                    continue
        
        return hierarchies
    
    def identify_event_patterns(self, events: List[Event]) -> List[EventPattern]:
        """Identify common patterns in event sequences"""
        
        # Group events by domain and type
        event_groups = defaultdict(list)
        for event in events:
            domain = event.properties.get("domain", "unknown")
            key = f"{domain}_{event.type}"
            event_groups[key].append(event)
        
        patterns = []
        
        for group_key, group_events in event_groups.items():
            domain, event_type = group_key.split("_", 1)
            
            # Look for patterns in event sequences
            event_sequences = []
            for event in group_events:
                if event.temporal_order:
                    event_sequences.append({
                        "id": event.id,
                        "order": event.temporal_order,
                        "actor": event.actor,
                        "target": event.target,
                        "description": event.properties.get("description", "")
                    })
            
            if len(event_sequences) >= 2:  # Need at least 2 events for a pattern
                pattern_prompt = f"""
                Analyze these {event_type} events in the {domain} domain to identify common patterns.
                Focus on patterns that are useful for troubleshooting and maintenance procedures.
                
                Events: {json.dumps(event_sequences, indent=2)}
                
                Identify patterns such as:
                1. Common sequences (events that often happen together)
                2. Diagnostic patterns (investigation → diagnosis → action)
                3. Maintenance patterns (check → service → verify)
                4. Safety patterns (lockout → service → test → restore)
                
                Return a JSON list of patterns:
                [
                    {{
                        "pattern_id": "unique_pattern_id",
                        "pattern_type": "diagnostic|maintenance|safety|operational",
                        "events": ["event1", "event2", "event3"],
                        "frequency": 1,
                        "domain": "{domain}",
                        "context": "when this pattern is used"
                    }}
                ]
                """
                
                try:
                    response = self.llm.invoke(pattern_prompt)
                    patterns_data = json.loads(response.content)
                    
                    for pattern_data in patterns_data:
                        pattern = EventPattern(
                            pattern_id=pattern_data["pattern_id"],
                            pattern_type=pattern_data["pattern_type"],
                            events=pattern_data["events"],
                            frequency=pattern_data["frequency"],
                            domain=pattern_data["domain"],
                            context=pattern_data["context"]
                        )
                        patterns.append(pattern)
                        
                except Exception as e:
                    print(f"Error identifying patterns for {group_key}: {e}")
                    continue
        
        return patterns
    
    def build_concept_networks(self, concepts: List[Concept]) -> List[ConceptNetwork]:
        """Build networks of related concepts"""
        
        # Group concepts by domain and type
        concept_groups = defaultdict(list)
        for concept in concepts:
            domain = concept.properties.get("domain", "unknown")
            concept_groups[domain].append(concept)
        
        networks = []
        
        for domain, domain_concepts in concept_groups.items():
            # Create concept network for this domain
            concept_info = []
            for concept in domain_concepts:
                concept_info.append({
                    "id": concept.id,
                    "type": concept.type,
                    "name": concept.properties.get("name", concept.id),
                    "description": concept.properties.get("description", ""),
                    "importance": concept.properties.get("importance", "medium")
                })
            
            network_prompt = f"""
            Create a network of related concepts in the {domain} domain.
            Focus on concepts that are interconnected for troubleshooting and maintenance.
            
            Concepts: {json.dumps(concept_info, indent=2)}
            
            For each concept, identify:
            1. Related concepts (what concepts are connected)
            2. Relationship types (how they are connected)
            3. Abstraction level (how abstract vs concrete)
            
            Return a JSON list of concept networks:
            [
                {{
                    "concept_id": "concept_id",
                    "related_concepts": ["related1", "related2"],
                    "relationship_types": ["supports", "requires", "conflicts_with"],
                    "domain": "{domain}",
                    "abstraction_level": 1
                }}
            ]
            
            Abstraction levels: 1=very abstract, 2=abstract, 3=concrete, 4=very concrete
            """
            
            try:
                response = self.llm.invoke(network_prompt)
                networks_data = json.loads(response.content)
                
                for network_data in networks_data:
                    network = ConceptNetwork(
                        concept_id=network_data["concept_id"],
                        related_concepts=network_data["related_concepts"],
                        relationship_types=network_data["relationship_types"],
                        domain=network_data["domain"],
                        abstraction_level=network_data["abstraction_level"]
                    )
                    networks.append(network)
                    
            except Exception as e:
                print(f"Error building concept network for {domain}: {e}")
                continue
        
        return networks
    
    def generate_domain_schemas(self, entities: List[Entity], events: List[Event], concepts: List[Concept]) -> List[DomainSchema]:
        """Generate comprehensive schemas for each domain"""
        
        # Collect all domains
        domains = set()
        for item in entities + events + concepts:
            domain = item.properties.get("domain", "unknown")
            domains.add(domain)
        
        schemas = []
        
        for domain in domains:
            # Filter items by domain
            domain_entities = [e for e in entities if e.properties.get("domain") == domain]
            domain_events = [e for e in events if e.properties.get("domain") == domain]
            domain_concepts = [c for c in concepts if c.properties.get("domain") == domain]
            
            # Collect types
            entity_types = list(set(e.type for e in domain_entities))
            event_types = list(set(e.type for e in domain_events))
            concept_types = list(set(c.type for c in domain_concepts))
            
            schema_prompt = f"""
            Create a comprehensive schema for the {domain} domain in LGV troubleshooting.
            
            Entity Types: {entity_types}
            Event Types: {event_types}
            Concept Types: {concept_types}
            
            Generate a domain schema that includes:
            1. Key relationship patterns common in this domain
            2. Key principles that govern this domain
            3. How this domain interacts with other domains
            
            Return a JSON object:
            {{
                "domain_name": "{domain}",
                "entity_types": {entity_types},
                "event_types": {event_types},
                "concept_types": {concept_types},
                "relationship_patterns": ["pattern1", "pattern2"],
                "key_principles": ["principle1", "principle2"]
            }}
            """
            
            try:
                response = self.llm.invoke(schema_prompt)
                schema_data = json.loads(response.content)
                
                schema = DomainSchema(
                    domain_name=schema_data["domain_name"],
                    entity_types=schema_data["entity_types"],
                    event_types=schema_data["event_types"],
                    concept_types=schema_data["concept_types"],
                    relationship_patterns=schema_data["relationship_patterns"],
                    key_principles=schema_data["key_principles"]
                )
                schemas.append(schema)
                
            except Exception as e:
                print(f"Error generating schema for {domain}: {e}")
                continue
        
        return schemas
    
    def export_schemas(self, schemas: Dict[str, Any], output_path: str):
        """Export schemas to JSON file"""
        
        # Convert dataclasses to dictionaries
        export_data = {}
        
        # Convert entity hierarchies
        export_data["entity_hierarchies"] = []
        for hierarchy in schemas["entity_hierarchies"]:
            export_data["entity_hierarchies"].append({
                "root_concept": hierarchy.root_concept,
                "hierarchy": hierarchy.hierarchy,
                "instances": hierarchy.instances,
                "domain": hierarchy.domain
            })
        
        # Convert event patterns
        export_data["event_patterns"] = []
        for pattern in schemas["event_patterns"]:
            export_data["event_patterns"].append({
                "pattern_id": pattern.pattern_id,
                "pattern_type": pattern.pattern_type,
                "events": pattern.events,
                "frequency": pattern.frequency,
                "domain": pattern.domain,
                "context": pattern.context
            })
        
        # Convert concept networks
        export_data["concept_networks"] = []
        for network in schemas["concept_networks"]:
            export_data["concept_networks"].append({
                "concept_id": network.concept_id,
                "related_concepts": network.related_concepts,
                "relationship_types": network.relationship_types,
                "domain": network.domain,
                "abstraction_level": network.abstraction_level
            })
        
        # Convert domain schemas
        export_data["domain_schemas"] = []
        for schema in schemas["domain_schemas"]:
            export_data["domain_schemas"].append({
                "domain_name": schema.domain_name,
                "entity_types": schema.entity_types,
                "event_types": schema.event_types,
                "concept_types": schema.concept_types,
                "relationship_patterns": schema.relationship_patterns,
                "key_principles": schema.key_principles
            })
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        print(f"Schemas exported to {output_path}")
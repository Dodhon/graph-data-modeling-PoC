"""
Temporal Extractor for Knowledge Graph Construction
Extracts temporal sequences, causal chains, and procedural logic from technical documentation
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from langchain_anthropic import ChatAnthropic
from .eec_graph_transformer import Entity, Event, Concept, Relationship, EECGraphDocument
import json
import re


@dataclass
class DiagnosticSequence:
    """Represents a temporal sequence of diagnostic steps"""
    id: str
    name: str
    description: str
    steps: List[Dict[str, Any]]
    domain: str
    prerequisites: List[str] = None
    success_criteria: List[str] = None
    
    def __post_init__(self):
        if self.prerequisites is None:
            self.prerequisites = []
        if self.success_criteria is None:
            self.success_criteria = []


@dataclass
class CausalChain:
    """Represents a cause-effect relationship chain"""
    id: str
    symptom: str
    investigation_steps: List[str]
    root_causes: List[str]
    solutions: List[str]
    verification_steps: List[str]
    domain: str
    confidence: float = 0.8


@dataclass
class PrerequisiteGraph:
    """Represents prerequisite relationships between events"""
    event_id: str
    prerequisites: List[str]
    conditions: List[str]
    safety_requirements: List[str]
    tools_required: List[str]
    
    def __post_init__(self):
        if self.conditions is None:
            self.conditions = []
        if self.safety_requirements is None:
            self.safety_requirements = []
        if self.tools_required is None:
            self.tools_required = []


@dataclass
class ConditionalLogic:
    """Represents conditional decision logic"""
    condition: str
    if_true_action: str
    if_false_action: str
    context: str
    domain: str


class TemporalExtractor:
    """
    Extracts temporal patterns, sequences, and causal relationships from EEC documents
    Specialized for troubleshooting and diagnostic procedures
    """
    
    def __init__(self, llm: ChatAnthropic):
        self.llm = llm
    
    def extract_temporal_patterns(self, eec_docs: List[EECGraphDocument]) -> Dict[str, Any]:
        """Main method to extract all temporal patterns from EEC documents"""
        
        # Combine all events and relationships across documents
        all_events = []
        all_relationships = []
        all_entities = []
        
        for doc in eec_docs:
            all_events.extend(doc.events)
            all_relationships.extend(doc.relationships)
            all_entities.extend(doc.entities)
        
        # Extract different types of temporal patterns
        diagnostic_sequences = self.extract_diagnostic_sequences(all_events, all_relationships)
        causal_chains = self.extract_causal_chains(all_entities, all_events, all_relationships)
        prerequisite_graphs = self.extract_prerequisite_graphs(all_events, all_relationships)
        conditional_logic = self.extract_conditional_logic(eec_docs)
        
        return {
            "diagnostic_sequences": diagnostic_sequences,
            "causal_chains": causal_chains,
            "prerequisite_graphs": prerequisite_graphs,
            "conditional_logic": conditional_logic
        }
    
    def extract_diagnostic_sequences(self, events: List[Event], relationships: List[Relationship]) -> List[DiagnosticSequence]:
        """Extract diagnostic procedures as temporal sequences"""
        
        # Filter for diagnostic and maintenance events
        diagnostic_events = [e for e in events if e.type in ["DIAGNOSTIC", "MAINTENANCE", "SAFETY"]]
        
        if not diagnostic_events:
            return []
        
        # Group events by domain and target
        event_groups = {}
        for event in diagnostic_events:
            key = f"{event.properties.get('domain', 'unknown')}_{event.target or 'general'}"
            if key not in event_groups:
                event_groups[key] = []
            event_groups[key].append(event)
        
        sequences = []
        
        for group_key, group_events in event_groups.items():
            # Create prompt for sequence extraction
            events_info = []
            for event in group_events:
                events_info.append({
                    "id": event.id,
                    "type": event.type,
                    "name": event.properties.get("name", event.id),
                    "description": event.properties.get("description", ""),
                    "temporal_order": event.temporal_order,
                    "actor": event.actor,
                    "target": event.target
                })
            
            sequence_prompt = f"""
            Analyze these diagnostic/maintenance events and create a logical temporal sequence.
            Focus on troubleshooting procedures for LGV (forklift) systems.
            
            Events: {json.dumps(events_info, indent=2)}
            
            Create a diagnostic sequence that shows:
            1. The logical order of steps
            2. Prerequisites for each step
            3. Conditions that trigger each step
            4. Success criteria for the sequence
            
            Return a JSON object with this structure:
            {{
                "id": "unique_sequence_id",
                "name": "sequence_name",
                "description": "what this sequence accomplishes",
                "domain": "hardware|software|environmental|human",
                "steps": [
                    {{
                        "order": 1,
                        "event_id": "event_id",
                        "action": "what to do",
                        "condition": "when to do it",
                        "expected_outcome": "what should happen",
                        "next_if_success": "next_step_if_successful",
                        "next_if_failure": "next_step_if_failed"
                    }}
                ],
                "prerequisites": ["what must be done first"],
                "success_criteria": ["how to know it worked"]
            }}
            """
            
            try:
                response = self.llm.invoke(sequence_prompt)
                sequence_data = json.loads(response.content)
                
                sequence = DiagnosticSequence(
                    id=sequence_data["id"],
                    name=sequence_data["name"],
                    description=sequence_data["description"],
                    steps=sequence_data["steps"],
                    domain=sequence_data["domain"],
                    prerequisites=sequence_data.get("prerequisites", []),
                    success_criteria=sequence_data.get("success_criteria", [])
                )
                sequences.append(sequence)
                
            except Exception as e:
                print(f"Error extracting sequence for {group_key}: {e}")
                continue
        
        return sequences
    
    def extract_causal_chains(self, entities: List[Entity], events: List[Event], relationships: List[Relationship]) -> List[CausalChain]:
        """Extract cause-effect chains for troubleshooting"""
        
        # Filter for symptoms and problems
        symptoms = [e for e in entities if e.type in ["SYMPTOM", "MEASUREMENT"] and 
                   any(word in e.properties.get("description", "").lower() 
                       for word in ["error", "fault", "failure", "problem", "low", "high", "abnormal"])]
        
        if not symptoms:
            return []
        
        causal_chains = []
        
        for symptom in symptoms:
            # Find related diagnostic events and solutions
            related_events = []
            related_solutions = []
            
            # Look for events that target this symptom or relate to it
            for event in events:
                if (event.target == symptom.id or 
                    symptom.id in event.properties.get("description", "") or
                    any(word in event.properties.get("description", "").lower() 
                        for word in symptom.properties.get("description", "").lower().split())):
                    if event.type == "DIAGNOSTIC":
                        related_events.append(event)
                    elif event.type in ["MAINTENANCE", "OPERATIONAL"]:
                        related_solutions.append(event)
            
            if related_events or related_solutions:
                causal_prompt = f"""
                Analyze this symptom and related events to create a causal troubleshooting chain.
                
                Symptom: {symptom.properties}
                Diagnostic Events: {[e.properties for e in related_events]}
                Solution Events: {[e.properties for e in related_solutions]}
                
                Create a causal chain that shows:
                1. What investigations should be done for this symptom
                2. What root causes might be found
                3. What solutions address each root cause
                4. How to verify the solution worked
                
                Return a JSON object:
                {{
                    "id": "unique_chain_id",
                    "symptom": "{symptom.id}",
                    "investigation_steps": ["step1", "step2"],
                    "root_causes": ["possible_cause1", "possible_cause2"],
                    "solutions": ["solution1", "solution2"],
                    "verification_steps": ["verify1", "verify2"],
                    "domain": "hardware|software|environmental|human",
                    "confidence": 0.8
                }}
                """
                
                try:
                    response = self.llm.invoke(causal_prompt)
                    chain_data = json.loads(response.content)
                    
                    chain = CausalChain(
                        id=chain_data["id"],
                        symptom=chain_data["symptom"],
                        investigation_steps=chain_data["investigation_steps"],
                        root_causes=chain_data["root_causes"],
                        solutions=chain_data["solutions"],
                        verification_steps=chain_data["verification_steps"],
                        domain=chain_data["domain"],
                        confidence=chain_data.get("confidence", 0.8)
                    )
                    causal_chains.append(chain)
                    
                except Exception as e:
                    print(f"Error extracting causal chain for {symptom.id}: {e}")
                    continue
        
        return causal_chains
    
    def extract_prerequisite_graphs(self, events: List[Event], relationships: List[Relationship]) -> List[PrerequisiteGraph]:
        """Extract prerequisite relationships between events"""
        
        prerequisite_graphs = []
        
        for event in events:
            # Find prerequisite relationships
            prerequisites = []
            conditions = []
            safety_requirements = []
            tools_required = []
            
            # Look for relationships that point to this event
            for rel in relationships:
                if rel.target == event.id:
                    if rel.type in ["REQUIRES", "DEPENDS_ON"]:
                        prerequisites.append(rel.source)
                    elif rel.type == "HAPPENS_BEFORE":
                        prerequisites.append(rel.source)
            
            # Extract from event properties
            if event.prerequisites:
                prerequisites.extend(event.prerequisites)
            
            # Look for safety and tool requirements in description
            description = event.properties.get("description", "").lower()
            if any(word in description for word in ["safety", "lockout", "disconnect", "depressurize"]):
                safety_requirements.append("safety_protocol_required")
            
            if any(word in description for word in ["tool", "equipment", "gauge", "meter"]):
                tools_required.append("specialized_tools_required")
            
            if prerequisites or conditions or safety_requirements or tools_required:
                prereq_graph = PrerequisiteGraph(
                    event_id=event.id,
                    prerequisites=prerequisites,
                    conditions=conditions,
                    safety_requirements=safety_requirements,
                    tools_required=tools_required
                )
                prerequisite_graphs.append(prereq_graph)
        
        return prerequisite_graphs
    
    def extract_conditional_logic(self, eec_docs: List[EECGraphDocument]) -> List[ConditionalLogic]:
        """Extract conditional decision logic from documentation"""
        
        conditional_logic = []
        
        for doc in eec_docs:
            # Look for conditional language in source text
            for event in doc.events:
                if event.source_chunk:
                    # Look for conditional patterns
                    conditional_patterns = [
                        r"if\s+(.+?)\s+then\s+(.+?)(?:\s+else\s+(.+?))?",
                        r"when\s+(.+?),\s+(.+?)(?:\s+otherwise\s+(.+?))?",
                        r"in case of\s+(.+?),\s+(.+?)(?:\s+if not\s+(.+?))?",
                    ]
                    
                    for pattern in conditional_patterns:
                        matches = re.finditer(pattern, event.source_chunk.lower(), re.IGNORECASE)
                        for match in matches:
                            condition = match.group(1).strip()
                            if_true = match.group(2).strip()
                            if_false = match.group(3).strip() if match.group(3) else "continue_normal_procedure"
                            
                            logic = ConditionalLogic(
                                condition=condition,
                                if_true_action=if_true,
                                if_false_action=if_false,
                                context=event.id,
                                domain=event.properties.get("domain", "unknown")
                            )
                            conditional_logic.append(logic)
        
        return conditional_logic
    
    def export_temporal_patterns(self, temporal_patterns: Dict[str, Any], output_path: str):
        """Export temporal patterns to JSON file"""
        
        # Convert dataclasses to dictionaries
        export_data = {}
        
        # Convert diagnostic sequences
        export_data["diagnostic_sequences"] = []
        for seq in temporal_patterns["diagnostic_sequences"]:
            export_data["diagnostic_sequences"].append({
                "id": seq.id,
                "name": seq.name,
                "description": seq.description,
                "steps": seq.steps,
                "domain": seq.domain,
                "prerequisites": seq.prerequisites,
                "success_criteria": seq.success_criteria
            })
        
        # Convert causal chains
        export_data["causal_chains"] = []
        for chain in temporal_patterns["causal_chains"]:
            export_data["causal_chains"].append({
                "id": chain.id,
                "symptom": chain.symptom,
                "investigation_steps": chain.investigation_steps,
                "root_causes": chain.root_causes,
                "solutions": chain.solutions,
                "verification_steps": chain.verification_steps,
                "domain": chain.domain,
                "confidence": chain.confidence
            })
        
        # Convert prerequisite graphs
        export_data["prerequisite_graphs"] = []
        for graph in temporal_patterns["prerequisite_graphs"]:
            export_data["prerequisite_graphs"].append({
                "event_id": graph.event_id,
                "prerequisites": graph.prerequisites,
                "conditions": graph.conditions,
                "safety_requirements": graph.safety_requirements,
                "tools_required": graph.tools_required
            })
        
        # Convert conditional logic
        export_data["conditional_logic"] = []
        for logic in temporal_patterns["conditional_logic"]:
            export_data["conditional_logic"].append({
                "condition": logic.condition,
                "if_true_action": logic.if_true_action,
                "if_false_action": logic.if_false_action,
                "context": logic.context,
                "domain": logic.domain
            })
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        print(f"Temporal patterns exported to {output_path}")
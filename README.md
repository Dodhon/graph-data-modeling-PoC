# LGV Troubleshooting Knowledge Graph

Entity-Event-Concept (EEC) knowledge graph extraction from technical documentation for LGV (forklift) troubleshooting and maintenance support.

## Overview

This pipeline transforms technical manuals into a comprehensive knowledge graph optimized for troubleshooting LGV malfunctions. It uses advanced LLM-powered extraction to identify entities, events, concepts, temporal sequences, and causal relationships.

## Features

### Core Capabilities
- **Entity-Event-Concept Extraction**: Identifies components, procedures, and abstract principles
- **Temporal Reasoning**: Extracts diagnostic sequences and causal chains
- **Schema Induction**: Creates hierarchical taxonomies and patterns
- **Multi-Domain Support**: Handles hardware, software, environmental, and human factors
- **Incremental Processing**: Updates Neo4j after each chunk for fault tolerance

### Extraction Types

#### Entities
- **COMPONENTS**: Mechanical parts, hydraulic elements, electrical components
- **TOOLS**: Diagnostic equipment, repair tools, measurement devices
- **PEOPLE**: Operators, technicians, engineers
- **SYMPTOMS**: Error codes, warning signals, performance issues
- **MEASUREMENTS**: Pressure readings, voltage levels, temperatures

#### Events
- **DIAGNOSTIC**: Inspection procedures, testing steps
- **MAINTENANCE**: Repair actions, replacements, adjustments
- **SAFETY**: Safety checks, lockout procedures
- **OPERATIONAL**: Startup, shutdown, normal operations
- **FAILURE**: Fault conditions, error states

#### Concepts
- **SAFETY_PRINCIPLES**: Safety rules, protective measures
- **DIAGNOSTIC_LOGIC**: Troubleshooting approaches
- **MAINTENANCE_CONCEPTS**: Preventive maintenance strategies
- **FAILURE_PATTERNS**: Common failure modes

## Quick Start

### Prerequisites
- Python 3.8+
- Anthropic API key (Claude access)
- Neo4j database (optional)

### Installation

1. **Clone repository:**
   ```bash
   git clone https://github.com/yourusername/graph-data-modeling-PoC.git
   cd graph-data-modeling-PoC
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment:**
   ```bash
   cp config/.env.example .env
   # Edit .env with your API keys:
   # - ANTHROPIC_API_KEY (required)
   # - NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD (optional)
   ```

### Running the Pipeline

**Full extraction:**
```bash
PYTHONPATH=. python3 scripts/run_graph_extraction.py
```

**Test with limited data:**
```python
# Modify line 41 in scripts/run_graph_extraction.py:
result = builder.build_graph_from_manual(manual_path, max_lines=100)
```

## Architecture

### Core Modules

- **`src/eec_graph_transformer.py`**: Extracts entities, events, and concepts using specialized LLM prompts
- **`src/temporal_extractor.py`**: Identifies diagnostic sequences, causal chains, and prerequisites
- **`src/schema_inducer.py`**: Creates hierarchical schemas and concept networks
- **`src/graph_builder.py`**: Orchestrates the complete pipeline

### Data Flow

1. **Input**: Technical manual text (`data/input/E80_manual_text.txt`)
2. **Preprocessing**: Cleans formatting, removes artifacts
3. **Chunking**: Splits into 800-character overlapping chunks
4. **EEC Extraction**: LLM analyzes each chunk for entities/events/concepts
5. **Temporal Processing**: Identifies sequences and causal relationships
6. **Schema Induction**: Creates hierarchies and patterns
7. **Storage**: Updates Neo4j incrementally, exports JSON

### Output Files

- **`e80_eec_knowledge_graph.json`**: Complete graph with entities, events, concepts, relationships
- **`e80_temporal_patterns.json`**: Diagnostic sequences, causal chains, prerequisites
- **`e80_schemas.json`**: Entity hierarchies, event patterns, concept networks

## Query Examples

### Find Diagnostic Procedure
```cypher
MATCH (s:Symptom {id: "low_hydraulic_pressure"})-[:INDICATES]->(cause:Entity)
MATCH (cause)-[:DIAGNOSED_BY]->(seq:DiagnosticSequence)
MATCH (seq)-[:CONTAINS]->(step:Event)
RETURN seq.name, step.action, step.temporal_order
ORDER BY step.temporal_order
```

### Get Causal Chain
```cypher
MATCH (symptom:Symptom)-[:INDICATES]->(root_cause:Entity)
MATCH (root_cause)-[:RESOLVED_BY]->(solution:Event)
RETURN symptom.description, root_cause.id, solution.action
```

### Find Required Tools
```cypher
MATCH (procedure:Event {type: "MAINTENANCE"})-[:REQUIRES]->(tool:Tool)
RETURN procedure.action, collect(tool.name) as required_tools
```

## Performance

- **Processing time**: ~3-4 hours for complete E80 manual (16,565 lines)
- **Chunk processing**: ~2000 chunks with 100-character overlap
- **Memory efficient**: Incremental processing and storage
- **Fault tolerant**: Progress saved every 100 chunks

## Use Cases

### Primary: LGV Troubleshooting
- Diagnose hydraulic system failures
- Find maintenance procedures
- Identify required tools
- Track safety prerequisites

### Future: Support Ticket Integration
- Link real incidents to manual procedures
- Validate solutions against documentation
- Build knowledge from resolved cases

## Project Structure

```
graph-data-modeling-PoC/
├── src/
│   ├── eec_graph_transformer.py    # Entity-Event-Concept extraction
│   ├── temporal_extractor.py       # Temporal pattern analysis
│   ├── schema_inducer.py           # Hierarchical schema creation
│   └── graph_builder.py            # Main pipeline orchestrator
├── scripts/
│   └── run_graph_extraction.py     # Entry point
├── data/
│   ├── input/
│   │   └── E80_manual_text.txt    # Source technical manual
│   └── output/                     # Generated JSON files
├── config/
│   └── .env.example                # Configuration template
└── requirements.txt                # Python dependencies
```

## Technical Stack

- **LLM**: Claude 3.5 Sonnet (via Anthropic API)
- **Framework**: LangChain for document processing
- **Database**: Neo4j for graph storage
- **Language**: Python 3.8+

## Contributing

This is a proof-of-concept for industrial knowledge graph construction. Contributions welcome for:
- Additional entity/event types
- Enhanced temporal reasoning
- Improved troubleshooting queries
- Multi-language support

## License

[Your License Here]
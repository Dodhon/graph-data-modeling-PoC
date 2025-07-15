# LGV Troubleshooting Knowledge Graph

Entity-Event-Concept (EEC) knowledge graph extraction from technical documentation for LGV (forklift) troubleshooting and maintenance support.

## Overview

This pipeline transforms technical manuals into a comprehensive knowledge graph optimized for troubleshooting LGV malfunctions. It uses advanced LLM-powered extraction to identify entities, events, concepts, temporal sequences, and causal relationships from unstructured technical documentation.

## Features

### Core Capabilities
- **Entity-Event-Concept Extraction**: Identifies components, procedures, and abstract principles using specialized LLM prompts
- **Temporal Reasoning**: Extracts diagnostic sequences, causal chains, and prerequisite relationships
- **Schema Induction**: Creates hierarchical taxonomies and domain-specific patterns
- **Multi-Domain Support**: Handles hardware, software, environmental, and human factors
- **Incremental Processing**: Updates Neo4j after each chunk for fault tolerance and progress tracking
- **Robust Error Handling**: Advanced JSON parsing with fallback mechanisms for malformed responses

### Extraction Types

#### Entities
- **COMPONENTS**: Mechanical parts, hydraulic systems, electrical components
- **TOOLS**: Diagnostic equipment, repair tools, measurement devices
- **PEOPLE**: Operators, technicians, engineers, manufacturers
- **LOCATIONS**: Facilities, plant locations, work areas
- **SYMPTOMS**: Error codes, warning signals, performance issues
- **MEASUREMENTS**: Pressure readings, voltage levels, temperatures

#### Events
- **DIAGNOSTIC**: Inspection procedures, testing steps, troubleshooting actions
- **MAINTENANCE**: Repair actions, replacements, adjustments, servicing
- **SAFETY**: Safety checks, lockout procedures, protective measures
- **OPERATIONAL**: Startup, shutdown, normal operations, procedures
- **FAILURE**: Fault conditions, error states, malfunction events

#### Concepts
- **SAFETY_PRINCIPLES**: Safety rules, protective measures, risk management
- **DIAGNOSTIC_LOGIC**: Troubleshooting approaches, decision trees
- **MAINTENANCE_CONCEPTS**: Preventive maintenance strategies, best practices
- **OPERATIONAL_PRINCIPLES**: Normal operation guidelines, standards
- **FAILURE_PATTERNS**: Common failure modes, root cause analysis
- **TECHNICAL_CONCEPTS**: Technical principles, domain knowledge, engineering concepts

#### Relationships
- **CAUSES**: Causal relationships between entities and events
- **REQUIRES**: Dependencies and prerequisites
- **PREVENTS**: Preventive relationships
- **DIAGNOSES**: Diagnostic connections
- **FIXES**: Solution relationships
- **APPLIES_TO**: Concept applications
- **PART_OF**: Hierarchical relationships
- **HAPPENS_BEFORE**: Temporal sequences
- **TRIGGERS**: Event triggering relationships

## Quick Start

### Prerequisites
- Python 3.8+
- Anthropic API key (Claude 3.5 Sonnet access)
- Neo4j database (optional for graph storage)

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

- **`src/eec_graph_transformer.py`**: Main extraction engine with specialized prompts for entities, events, concepts, and relationships
- **`src/temporal_extractor.py`**: Identifies diagnostic sequences, causal chains, and prerequisite graphs
- **`src/schema_inducer.py`**: Creates hierarchical schemas, concept networks, and domain taxonomies
- **`src/graph_builder.py`**: Orchestrates the complete pipeline with incremental processing and error recovery

### Data Flow

1. **Input**: Technical manual text (`data/input/E80_manual_text.txt`)
2. **Preprocessing**: Removes page markers, line numbers, and normalizes whitespace
3. **Chunking**: Splits into 800-character overlapping chunks (100-character overlap)
4. **EEC Extraction**: Claude 3.5 Sonnet analyzes each chunk for:
   - Entities (concrete objects and components)
   - Events (actions and procedures)
   - Concepts (abstract principles and knowledge)
   - Relationships (connections between items)
5. **Temporal Processing**: Identifies sequences, causal chains, and conditional logic
6. **Schema Induction**: Creates hierarchies, patterns, and domain-specific schemas
7. **Storage**: Updates Neo4j incrementally after each chunk, exports comprehensive JSON files

### Technical Configuration

**LLM Settings:**
- Model: Claude 3.5 Sonnet (claude-3-5-sonnet-20241022)
- Temperature: 0 (deterministic outputs)
- Max tokens: 8192
- Timeout: 90 seconds with 3 retries

**Processing Settings:**
- Chunk size: 800 characters
- Chunk overlap: 100 characters
- Rate limiting: 3-second pause every 20 chunks
- Progress saves: Every 100 chunks

### Output Files

- **`e80_eec_knowledge_graph.json`**: Complete graph with entities, events, concepts, and relationships
- **`e80_temporal_patterns.json`**: Diagnostic sequences, causal chains, prerequisite graphs, conditional logic
- **`e80_schemas.json`**: Entity hierarchies, event patterns, concept networks, domain schemas
- **Progress files**: Incremental saves during processing (`*_progress_*.json`)

## Query Examples

### Find Components and Their Relationships
```cypher
MATCH (c:Entity {type: "COMPONENT"})
OPTIONAL MATCH (c)-[r]->(related)
RETURN c.name, c.description, type(r), related.name
LIMIT 10
```

### Get Diagnostic Procedures
```cypher
MATCH (d:Event {type: "DIAGNOSTIC"})
RETURN d.name, d.description, d.domain
ORDER BY d.name
```

### Find Causal Relationships
```cypher
MATCH (source)-[:CAUSES]->(target)
RETURN source.name, target.name, source.type, target.type
```

### Get Safety-Related Concepts
```cypher
MATCH (c:Concept {type: "SAFETY_PRINCIPLES"})
RETURN c.name, c.description, c.importance
```

## Performance

- **Processing time**: ~3-4 hours for complete E80 manual (16,565 lines)
- **Total chunks**: 1,099 chunks with 100-character overlap
- **Memory efficient**: Incremental processing with progress saves
- **Fault tolerant**: Automatic recovery from interruptions
- **Rate limited**: Built-in delays to prevent API throttling

### Current Processing Metrics
- **Entities extracted**: ~1,200+ per 300 chunks processed
- **Events extracted**: ~650+ per 300 chunks processed
- **Concepts extracted**: ~950+ per 300 chunks processed
- **Relationships extracted**: ~1,200+ per 300 chunks processed

## Use Cases

### Primary: LGV Troubleshooting
- Diagnose hydraulic system failures
- Find maintenance procedures and requirements
- Identify required tools and components
- Track safety prerequisites and protocols
- Analyze failure patterns and root causes

### Query-Based Troubleshooting
- "What tools are required for hydraulic pump maintenance?"
- "What are the safety prerequisites for electrical system work?"
- "What diagnostic steps should I follow for low pressure symptoms?"
- "What components are part of the hydraulic system?"

### Future: Support Ticket Integration
- Link real incidents to manual procedures
- Validate solutions against documentation
- Build knowledge from resolved cases
- Create automated troubleshooting workflows

## Error Handling and Robustness

### JSON Response Processing
- Advanced parsing for both array and object formats
- Bracket/brace counting for proper JSON extraction
- Fallback mechanisms for malformed responses
- Content validation before processing

### Rate Limiting and Recovery
- Built-in delays to prevent API throttling
- Connection error recovery with extended delays
- Progress preservation on failures
- Automatic retry mechanisms

### Data Validation
- Property filtering for Neo4j compatibility
- Relationship validation between verified entities
- Empty value handling and cleanup
- Source chunk tracking for debugging

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
│   │   └── E80_manual_text.txt     # Source technical manual
│   └── output/                     # Generated JSON files
├── config/
│   └── .env.example                # Configuration template
└── requirements.txt                # Python dependencies
```

## Technical Stack

- **LLM**: Claude 3.5 Sonnet (via Anthropic API)
- **Framework**: LangChain for document processing
- **Database**: Neo4j for graph storage (optional)
- **Language**: Python 3.8+
- **Processing**: Incremental chunking with overlap

## Contributing

This is a proof-of-concept for industrial knowledge graph construction. Contributions welcome for:
- Additional entity/event/concept types
- Enhanced temporal reasoning algorithms
- Improved troubleshooting query patterns
- Multi-language support
- Performance optimizations
- Cross-chunk relationship detection

## License

[Your License Here]
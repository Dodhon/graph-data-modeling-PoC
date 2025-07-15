# Graph Data Modeling PoC

Knowledge graph construction from technical documentation using LangChain and AutoSchemaKG-inspired approaches.

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your OpenAI API key
   ```

3. **Run extraction:**
   ```bash
   python run_graph_extraction.py
   ```

## Features

- **LLM-powered triple extraction** using LangChain's LLMGraphTransformer
- **Domain-specific entity recognition** for technical manuals
- **Automated graph construction** from unstructured text
- **Neo4j integration** for graph storage and querying
- **JSON export** for visualization and analysis

## Architecture

- `src/graph_builder.py` - Core graph construction logic
- `run_graph_extraction.py` - Simple runner script
- `E80_manual_text.txt` - Input technical manual (900 pages)

## Entity Types

The system recognizes technical manual entities:
- Machine, Component, System, Part
- Procedure, Maintenance_Task, Tool
- Safety_Rule, Warning, Specification
- Company, Location, Document, Standard
# OpenAI RAG System for E80 Manual

A Retrieval-Augmented Generation (RAG) system using OpenAI's Assistants API with file search capabilities for the E80 troubleshooting manual.

## Features

- **Vector Store Management**: Automatic creation and management of OpenAI vector stores
- **File Search**: Leverages OpenAI's built-in file search with semantic and keyword search
- **Interactive Querying**: Command-line interface for asking questions about the E80 manual
- **Batch Processing**: Process multiple questions from a file
- **Test Suite**: Validate RAG functionality with predefined test queries

## Setup

### Prerequisites

1. OpenAI API key in your `.env` file:
   ```
   OPENAI_API_KEY=your-api-key-here
   ```

2. E80 manual text file at: `data/input/E80_manual_text.txt`

### Installation

No additional dependencies needed - uses the same requirements as the main project.

### Initial Setup

Run the setup script to create the vector store and upload the manual:

```bash
cd rag_system
python setup_rag.py
```

This will:
- Create a new vector store in OpenAI
- Upload the E80 manual
- Create an assistant configured for troubleshooting
- Save configuration to `rag_config.json`

## Usage

### Interactive Mode (Default)

```bash
python query_rag.py
```

Start an interactive session where you can ask questions continuously.

### Single Question

```bash
python query_rag.py -q "How do I troubleshoot hydraulic pressure issues?"
```

### Batch Processing

Create a file with questions (one per line):
```bash
python query_rag.py -f questions.txt
```

Results will be saved to `questions_answers.json`.

### Test the System

Run the test suite to validate functionality:
```bash
python test_queries.py
```

## Example Queries

- "What are the main components of the hydraulic system?"
- "How do I troubleshoot low hydraulic pressure?"
- "What safety procedures should be followed for electrical work?"
- "What are common error codes and their meanings?"
- "How often should hydraulic fluid be changed?"

## How It Works

1. **Vector Store**: The E80 manual is automatically chunked and embedded by OpenAI
2. **File Search**: When you ask a question, OpenAI searches the vector store for relevant content
3. **Augmented Response**: The assistant uses retrieved context to provide accurate, manual-based answers
4. **Citations**: Responses include references to specific procedures and sections when applicable

## Costs

- **Vector Store**: 1GB free tier, then $0.10/GB/month
- **API Calls**: Standard OpenAI API pricing for GPT-4-turbo
- **File Storage**: Minimal cost for storing the uploaded manual

## Integration with Knowledge Graph

This RAG system complements the existing knowledge graph extraction:
- **Graph**: Structured relationships between entities, events, and concepts
- **RAG**: Natural language access to full manual content
- **Hybrid**: Combine graph queries with RAG for comprehensive troubleshooting

## Troubleshooting

1. **"Configuration not found"**: Run `setup_rag.py` first
2. **"API key not found"**: Ensure `OPENAI_API_KEY` is in your `.env` file
3. **"Manual not found"**: Check that `data/input/E80_manual_text.txt` exists
4. **Rate limits**: OpenAI has rate limits - the system handles these automatically with retries
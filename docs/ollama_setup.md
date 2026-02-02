## Ollama Setup (Local)

This project uses Ollama to run Llama 3.1 locally for node deduplication.

### 1) Install Ollama
- macOS (recommended):
  - Download from: https://ollama.com/download
  - Or use Homebrew: `brew install ollama`

### 2) Start the Ollama server
```
ollama serve
```
By default, the server runs at `http://localhost:11434`.

### 3) Pull the model
Recommended for 16GB unified memory:
```
ollama pull llama3.1:8b-instruct-q6_K
```
Higher quality (more memory):
```
ollama pull llama3.1:8b-instruct-q8_0
```

### 4) Sanity check the model
```
ollama run llama3.1:8b-instruct-q6_K "Say hello in one sentence."
```

### 5) Run dedupe script
Edit the config at the top of:
- `scripts/dedupe_nodes_with_ollama.py`

Then run:
```
PYTHONPATH=. python3 scripts/dedupe_nodes_with_ollama.py
```

### 6) Checkpoints and resume
The script writes checkpoints during long runs:
- `data/dedupe/run_<timestamp>/checkpoint.json`

To resume after interruption, set in the script:
```
RESUME_FROM = "data/dedupe/run_<timestamp>/checkpoint.json"
```

### Notes
- Single instance recommended on 16GB machines.
- If you change the model name, update `OLLAMA_MODEL` in the script.
- Ollama API docs: https://docs.ollama.com/api/chat

## Quick Start

### Requirements

- Python 3.10–3.13 (LiteLLM does not support 3.14+)
- Node.js 18+ and npm
- At least one LLM provider API key (DeepSeek / OpenAI / Anthropic)

### Steps

```bash
# 1. Configure backend secrets
cd food-mate-api
cp .env.example .env        # Edit .env and fill in your real API key(s)

# 2. Go back to the root and start everything with one command (auto-installs dependencies, launches Proxy + API + Web)
cd ..
./start.sh
```

Once started, open:

- Web login page: http://127.0.0.1:3000/login

### 
### Troubleshooting

- **Python not found / incompatible version**: The script uses the conda env `/opt/miniconda3/envs/py311` by default. If your path differs, point it to a Python 3.10–3.13 interpreter via an environment variable:

  ```bash
  export FOODMATE_CONDA_ENV=/path/to/conda/envs/py311   # specify the env directory
  # or
  export FOODMATE_PYTHON=/path/to/bin/python            # specify the interpreter directly
  ```

- **Port already in use**: The script refuses to start if port 3000 or 8000 is occupied. Free the ports, or use custom ones:
  ```bash
  FOODMATE_WEB_PORT=3001 FOODMATE_API_PORT=8001 ./start.sh
  ```




  

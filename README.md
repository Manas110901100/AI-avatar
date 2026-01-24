# AI Avatar – Real-Time 3D Talking Agent

A web-based application featuring a fully animated 3D avatar that speaks with users in real time. The system uses a Three.js front-end and a Python FastAPI backend to handle LLM-powered dialogue and text-to-speech audio generation, with dynamic lip-sync (visemes), automatic eye blinking, and gesture blending for a lifelike experience.

---

## Features

- **Fully Animated 3D Avatar**  
  Renders an interactive 3D character in the browser using HTML/JS assets under `static/` (Three.js-based experience).

- **Real-Time Conversation**  
  Backend built with FastAPI (`main.py`) handles user messages, routes them through AI models, and streams responses back to the avatar.

- **LLM Integration**  
  AI models and prompts are managed in `aimodels.py`, allowing you to plug in LLM providers for intelligent conversations.

- **Text-to-Speech Pipeline**  
  `texttospeech.py` converts generated text into audio, which is synchronized with mouth movements (visemes) on the avatar.

- **Lip-Sync, Blinking, and Gestures**  
  The front-end coordinates audio playback with mouth shapes, automatic eye blinking, and gesture blending for natural animations.

- **Configurable & Extensible**  
  Supporting modules like `models.py`, `database.py`, and `api_validator.py` make it easier to validate requests, store data, and extend functionality.

---

## Project Structure

```text
AI-avatar/
├─ static/             # Front-end assets (HTML, JS, CSS, 3D scene, animations)
├─ aimodels.py         # LLM / AI model integration and prompt logic
├─ api_validator.py    # Request/response validation helpers (FastAPI/Pydantic)
├─ database.py         # Database or persistence layer utilities
├─ main.py             # FastAPI application entry point
├─ models.py           # Data models / schemas for API and internal use
├─ texttospeech.py     # Text-to-speech generation and audio handling
├─ requirements.txt    # Python dependencies
└─ .gitignore          # Ignore rules for local / build artifacts
```

##  Installation & Setup
### 1. Clone the Repository
```bash
git clone https://github.com/Manas110901100/AI-avatar.git
cd AI-avatar
```

### 2. Create & Activate Virtual Environment (Recommended)
```bash
# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (macOS / Linux)
source .venv/bin/activate
```
### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment
Depending on your AI and TTS providers, you will likely need API keys (e.g., for LLMs or text-to-speech). Typical setup:

Create a .env file or export environment variables with your API keys.

Update configuration in aimodels.py and texttospeech.py to point to your chosen models and services.

Adjust any database or storage parameters in database.py if persistence is used.

## Running the Application
From the project root:

``` bash
uvicorn main:app --reload
```
Then open the front-end (usually served via files in static/) in your browser. Depending on your setup, you might:

Serve static/ via FastAPI’s static files configuration in main.py, or

Open a specific HTML file (e.g., static/index.html) that connects to the FastAPI backend via WebSocket/HTTP.

Check main.py for the exact host, port, and routing configuration.

## How It Works
User speaks or types to the avatar through the web UI (front-end in static/).

FastAPI backend (main.py) receives the request and validates it via api_validator.py and models.py.

LLM module in aimodels.py generates a natural language response.

Text-to-speech in texttospeech.py converts the reply into audio.

The front-end plays the audio and drives animations (visemes, eye blinks, gestures) to synchronize the avatar’s movement with the speech.[page:1]


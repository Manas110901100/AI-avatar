import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))  # TTS_PROVIDER, LIPSYNC and voice-service keys; see plan.md

from aimodels import generate_performance
from api_validator import validate_and_save_api_key
from fastapi import Depends, FastAPI, Request
from models import ApiKeyRequest, Base, ChatRequest, LogResponse, ConversationLog, ApiKeyResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import database
from typing import List
from fastapi.responses import FileResponse
from voices import synthesize
from performance import build_timeline
from gestures import catalog
import base64
import tempfile


app = FastAPI()
Base.metadata.create_all(bind=database.engine)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    with open("request_logs.txt", "a") as f:
        f.write(f"REQ: {request.method} {request.url}\n")
    
    response = await call_next(request)
    
    with open("request_logs.txt", "a") as f:
        f.write(f"RES: {response.status_code}\n")
    return response

app.mount("/static", StaticFiles(directory="static"), name="static")

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
def home():
    return FileResponse("static/index.html")


@app.post("/keys/validate", response_model=ApiKeyResponse)
def register_key(request: ApiKeyRequest, db: Session = Depends(get_db)):
    db_key = validate_and_save_api_key(request, db)
    
    return db_key

@app.get("/keys/validate")
def register_key_get():
    return {"detail": "GET method not allowed. Please use POST. Error 405 diagnosis confirmed."}

@app.get("/chat/history/{api_key_id}", response_model=List[LogResponse])
def get_chat_history(api_key_id: int, db: Session = Depends(get_db)):
    logs = db.query(ConversationLog).filter(ConversationLog.api_key_id == api_key_id).all()
    if not logs:
        return []
    return logs

@app.get("/gestures")
def get_gestures():
    return catalog()

@app.post("/chat/speak")
def chat_with_audio(request: ChatRequest, db: Session = Depends(get_db)):

    script = generate_performance(
        user_input=request.input,
        api_key_id=request.api_key_id,
        model_name=request.model,
        db=db
    )

    ai_text = script.spoken_text

    # A folder per request, so simultaneous requests never share audio files
    with tempfile.TemporaryDirectory() as workdir:
        speech = synthesize(script, workdir)

    return {
        "text": ai_text,
        "audio": base64.b64encode(speech.audio).decode("ascii"),
        "audio_mime": speech.mime,
        "lipsync": speech.lipsync,
        "visemes": speech.visemes,
        "blendshapes": speech.blendshapes,
        "voice": speech.provider,
        "timeline": build_timeline(script, speech.words, speech.lipsync),
    }

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


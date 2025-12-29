from aimodels import generate_chat_response
from api_validator import validate_and_save_api_key
from fastapi import Depends, FastAPI, Request
from models import ApiKeyRequest, Base, ChatRequest, LogResponse, ConversationLog, ApiKeyResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import database
from typing import List
from fastapi.responses import FileResponse
from texttospeech import mp3_to_wav_ffmpeg, WAV_FILE, run_rhubarb
import base64


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

@app.post("/chat/speak")
def chat_with_audio(request: ChatRequest, db: Session = Depends(get_db)):
    
    chat_result = generate_chat_response(
        user_input=request.input, 
        api_key_id=request.api_key_id, 
        model_name=request.model,
        db=db
    )
    
    ai_text = chat_result.response
    
    output_filename = f"response_{request.api_key_id}.wav"
    wav_file_path = mp3_to_wav_ffmpeg(ai_text)
    
    lip_sync_data = ""
    try:
        lip_sync_data = run_rhubarb(wav_file_path)
        lip_sync_data = base64.b64encode(lip_sync_data.encode('utf-8')).decode('utf-8')
    except Exception as e:
        print(f"Rhubarb Error: {e}")
        # Continue without lip sync data if it fails
        lip_sync_data = ""

    return FileResponse(
        path=wav_file_path, 
        media_type="audio/wav", 
        filename="response.wav", 
        headers={
            "X-Animation-File": chat_result.animation,
            "X-Response-Text": ai_text,
            "X-Lip-Sync-Data": lip_sync_data
        }
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


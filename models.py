from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
from gestures import GestureName

class ApiKey(Base):
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    apikey = Column(String, unique=True, index=True)
    llm = Column(String)
    logs = relationship("ConversationLog", back_populates="api_key_owner")

class ConversationLog(Base):
    __tablename__ = "conversation_logs" 
    id = Column(Integer, primary_key=True, index=True)
    api_key_id = Column(Integer, ForeignKey("api_keys.id"))
    user_input = Column(String)
    ai_response = Column(String)
    animation = Column(String)
    api_key_owner = relationship("ApiKey", back_populates="logs")


Emotion = Literal[
    "neutral", "confident", "amused", "happy", "warm", "excited", "thoughtful",
    "curious", "skeptical", "serious", "sad", "surprised", "annoyed",
]
Gaze = Literal["camera", "away_left", "away_right", "up", "down"]
HeadMove = Literal["none", "nod", "small_nod", "tilt", "shake", "chin_up", "lean_in"]
Shot = Literal["wide", "medium", "close", "push_in"]
Hand = Literal["left", "right", "both"]
Delivery = Literal["normal", "whisper", "laugh", "sigh", "emphatic"]


class Beat(BaseModel):
    text: str = Field(..., description="One sentence or short phrase of the spoken reply, exactly as it should be spoken.")
    emotion: Emotion = Field(..., description="The feeling behind this line; the face shifts just before it is spoken.")
    intensity: float = Field(0.5, description="How strongly the emotion shows, 0.0 (barely) to 1.0 (fully).")
    gesture: Optional[GestureName] = Field(None, description="At most one gesture for this line, or null. Most lines should be null.")
    hand: Hand = Field("right", description="Which hand performs a live hand gesture.")
    count: Optional[int] = Field(None, description="Number of fingers (1-5) for the 'count' gesture; otherwise null.")
    force: float = Field(0.5, description="Gesture size and speed, 0.0 (subtle) to 1.0 (emphatic).")
    stress_word: Optional[str] = Field(None, description="The single word from this line that carries the emphasis; the gesture lands on it. Copy it exactly.")
    gaze: Gaze = Field("camera", description="Where the eyes go during this line. Look away only while reflecting; it returns to camera on the stress word.")
    head: HeadMove = Field("none", description="A head movement on the stress word.")
    shot: Shot = Field("medium", description="Camera framing for this line.")
    delivery: Delivery = Field("normal", description="How the voice performs the line: whisper, laugh, sigh, emphatic, or normal.")


class PerformanceScript(BaseModel):
    beats: List[Beat] = Field(..., description="The reply as 1 to 5 beats, in speaking order.")

    @property
    def spoken_text(self) -> str:
        return " ".join(beat.text.strip() for beat in self.beats if beat.text.strip())


class ApiResponse(BaseModel):
    message: str 

class ApiKeyRequest(BaseModel):
    api_key: str = Field(..., description="The OpenAI API key to validate.")

class ChatRequest(BaseModel):
    input: str = Field(..., description="The user's input text.")
    api_key_id: int = Field(..., description="API key identifier to use for this chat session.")
    model: str = Field(..., description="The model name used for generating responses.")

class ApiKeyResponse(BaseModel):
    id: int
    apikey: str
    llm: str

    class Config:
        from_attributes = True

class LogResponse(BaseModel):
    id: int
    user_input: str
    ai_response: str
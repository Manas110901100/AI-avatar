from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

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

      
AnimationType = Literal[
    "acknowledging.glb",
    "angry gesture.glb",
    "annoyed head shake.glb",
    "being cocky.glb",
    "Disappointed.glb",
    "dismissing gesture.glb",
    "happy hand gesture.glb",
    "hard head nod.glb",
    "head nod yes.glb",
    "lengthy head nod.glb",
    "look away gesture.glb",
    "relieved sigh.glb",
    "sarcastic head nod.glb",
    "shaking head no.glb",
    "Telling A Secret.glb",
    "thoughtful head shake.glb",
    "Yelling.glb"
]

class ChatModelResponse(BaseModel):
    response: str = Field(..., description="The spoken text response for the user.")
    animation: AnimationType = Field(..., description="The specific 3D animation file to play along with the text.")


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
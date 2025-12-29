from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from openai import OpenAI, OpenAIError, AuthenticationError
import models


def validate_and_save_api_key(request_data, db: Session):
    raw_key = request_data.api_key
    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="API Key is missing."
        )
    
    api_key = raw_key.strip()

    # 2. Format Validation (Fail Fast)
    if not api_key.startswith("sk-"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid API Key format provided. OpenAI keys must start with 'sk-'."
        )
    # 3. Database Check (Idempotency)
    try:
        existing_key = db.query(models.ApiKey).filter(models.ApiKey.apikey == api_key).first()
        if existing_key:
            return existing_key
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal database error during validation. or Invalid API Key."
        )

    # 4. External Verification (OpenAI API)
    try:
        client = OpenAI(api_key=api_key)
        client.models.list(timeout=5.0) 
        
    except AuthenticationError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The provided API Key is invalid or expired."
        )
    except OpenAIError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, 
            detail="Failed to verify key with OpenAI provider. Please try again later."
        )

    try:
        new_entry = models.ApiKey(apikey=api_key, llm="openai")
        db.add(new_entry)
        db.commit()
        db.refresh(new_entry)
        
        return new_entry

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save API Key to database."
        )
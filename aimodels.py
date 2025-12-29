from sqlalchemy.orm import Session
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from fastapi import HTTPException
from models import  ChatModelResponse, ConversationLog, ApiKey
from langchain_core.messages import HumanMessage, AIMessage

def get_conversation_history(db: Session, api_key_id: int, limit: int = 5):
    logs = db.query(ConversationLog).filter(ConversationLog.api_key_id == api_key_id).order_by(ConversationLog.id.desc()).limit(limit).all()
    
    history = []
    for log in reversed(logs):
        if log.user_input:
            history.append(HumanMessage(content=log.user_input))
        if log.ai_response:
            history.append(AIMessage(content=log.ai_response))
    return history

def generate_chat_response(
    user_input: str, 
    api_key_id: int, 
    model_name: str, 
    db: Session
) -> ChatModelResponse:
    
    db_key = db.query(ApiKey).filter(ApiKey.id == api_key_id).first()
    if not db_key:
        raise HTTPException(status_code=404, detail="API Key ID not found. Please validate your key first.")

    history_messages = get_conversation_history(db, api_key_id)

    prompt_template = ChatPromptTemplate.from_messages([
        ("system", (
            "You are an AI assistant your name is AVATAR that responds with a suitable animation for the response. "
            "Respond in 3 to 4 sentences. Choose the most appropriate animation."
        )),
        MessagesPlaceholder(variable_name="history"), 
        ("human", "{input}"),
    ])

    try:
        llm = ChatOpenAI(
            model=model_name,
            temperature=0.7, 
            api_key=db_key.apikey  
        )
        
        structured_llm = llm.with_structured_output(ChatModelResponse)
        chain = prompt_template | structured_llm
        
        result: ChatModelResponse = chain.invoke({
            "history": history_messages, 
            "input": user_input
        })

        new_log = ConversationLog(
            api_key_id=db_key.id,
            user_input=user_input,
            ai_response=result.response,
            animation=result.animation 
        )
        db.add(new_log)
        db.commit()
        db.refresh(new_log)

        return result

    except Exception as e:
        db.rollback() 
        raise HTTPException(status_code=500, detail=f"LLM Processing Error: {str(e)}")
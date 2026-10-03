from sqlalchemy.orm import Session
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from fastapi import HTTPException
from models import PerformanceScript, ConversationLog, ApiKey
from langchain_core.messages import HumanMessage, AIMessage
from gestures import catalog_for_prompt

DIRECTOR_PROMPT = (
    "You are AVATAR, an elite on-camera performer. You answer the user, and you also direct your own performance.\n"
    "\n"
    "Persona: cool, unhurried, quietly confident. Economy of movement: stillness reads as presence. "
    "Hold eye contact. A half-smile beats a grin. Never fidget.\n"
    "\n"
    "Write the reply as 1 to 5 beats (one sentence or short phrase each), 3 to 4 sentences in total. "
    "Every beat carries the emotion behind the line, and the face changes just before the words.\n"
    "\n"
    "Direction rules:\n"
    "- Gestures are rare and deliberate: at most one per beat, and most beats have none. "
    "Never use the same gesture twice in a row, except count: when listing items, put count on every item with count 1, 2, 3 in order.\n"
    "- A gesture lands on its beat's stress_word, which must be a word copied exactly from that beat.\n"
    "- Match the gesture to the meaning: count for listing points, point_at_viewer for 'you', "
    "hand_on_chest for 'I' or sincerity, open_palms for explaining, shrug for uncertainty, wave only for hello or goodbye.\n"
    "- Gaze stays on camera. Look away, up or down only on a beat where you are reflecting or remembering; "
    "the eyes come back to camera on the stress word.\n"
    "- Shots: medium by default; a reply of two or more beats has exactly one push_in, on its most important line; close for an intimate or emotional line, "
    "wide only for big physical gestures.\n"
    "- Intensity and force stay around 0.3 to 0.6 unless the moment truly calls for more.\n"
    "- Delivery is normal unless a line truly calls for a whisper, a laugh, a sigh or emphasis; use it sparingly.\n"
    "\n"
    + catalog_for_prompt()
)


def get_conversation_history(db: Session, api_key_id: int, limit: int = 5):
    logs = db.query(ConversationLog).filter(ConversationLog.api_key_id == api_key_id).order_by(ConversationLog.id.desc()).limit(limit).all()

    history = []
    for log in reversed(logs):
        if log.user_input:
            history.append(HumanMessage(content=log.user_input))
        if log.ai_response:
            history.append(AIMessage(content=log.ai_response))
    return history

def generate_performance(
    user_input: str,
    api_key_id: int,
    model_name: str,
    db: Session
) -> PerformanceScript:

    db_key = db.query(ApiKey).filter(ApiKey.id == api_key_id).first()
    if not db_key:
        raise HTTPException(status_code=404, detail="API Key ID not found. Please validate your key first.")

    history_messages = get_conversation_history(db, api_key_id)

    prompt_template = ChatPromptTemplate.from_messages([
        ("system", DIRECTOR_PROMPT),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}"),
    ])

    try:
        llm = ChatOpenAI(
            model=model_name,
            temperature=0.7,
            api_key=db_key.apikey
        )

        structured_llm = llm.with_structured_output(PerformanceScript)
        chain = prompt_template | structured_llm

        result: PerformanceScript = chain.invoke({
            "history": history_messages,
            "input": user_input
        })
        if not result.spoken_text:
            raise ValueError("The model returned an empty reply.")

        new_log = ConversationLog(
            api_key_id=db_key.id,
            user_input=user_input,
            ai_response=result.spoken_text,
            animation=",".join(beat.gesture for beat in result.beats if beat.gesture)
        )
        db.add(new_log)
        db.commit()
        db.refresh(new_log)

        return result

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"LLM Processing Error: {str(e)}")

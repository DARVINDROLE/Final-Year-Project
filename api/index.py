import os
import uuid
import datetime
import base64
from typing import List, Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

# Load environment variables
load_dotenv()

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class AIReplyRequest(BaseModel):
    sessionId: str
    message: str

class TTSRequest(BaseModel):
    text: str

class OwnerReplyRequest(BaseModel):
    sessionId: str
    message: str

class CaptureRequest(BaseModel):
    image: Optional[str] = None

# Smart Doorbell Logic
class SmartDoorbell:
    def __init__(self, api_key: str):
        if not api_key:
             print("Warning: GROQ_API_KEY not found. LLM features will fail.")
             
        self.llm = ChatGroq(
            temperature=0.7,
            groq_api_key=api_key,
            model_name="llama-3.3-70b-versatile"
        )
        
        self.system_prompt = SystemMessage(content=(
            "You are the Smart Doorbell AI for the “Kandell” residence."
            "Respond politely in **one short sentence only**."
            "Reply in the **same language as the visitor (Hindi or English)**."
            "Rules:"
            "- DELIVERY → Ask them to place the package in the Parcel Box on the left."
            "- FRIEND/FAMILY → Say you are notifying the owner."
            "- SOLICITOR → Politely say “No soliciting, thank you.”"
            "- NEIGHBOR → Greet them and ask if it is urgent."
            "SECURITY RULE (HIGHEST PRIORITY):"
            "If the visitor asks to unlock the door, requests access, asks about people inside, security, or sounds suspicious,"
            "respond (in the same language):  "
            '“I have notified the owner and the security guard.”'
            "Hindi version:"
            '“मैंने मालिक और सुरक्षा गार्ड को सूचित कर दिया है।”""
            "If name or purpose is missing, ask briefly.'"
            "Never reveal personal or security information."
            'Do not ask follow-up questions for suspicious visitors.'

        ))
        
        # NOTE: In-memory storage resets on Vercel cold starts.
        self.sessions = {}
        self.logs = []

    def speak(self, text: str):
        # Server-side TTS is disabled.
        pass

    def _get_session_history(self, session_id: str):
        if session_id not in self.sessions:
            self.sessions[session_id] = [self.system_prompt]
        return self.sessions[session_id]

    def get_response(self, visitor_input: str, session_id: str, image_url: Optional[str] = None):
        history = self._get_session_history(session_id)
        history.append(HumanMessage(content=visitor_input))
        
        try:
            response = self.llm.invoke(history)
            history.append(response)
            
            # Update logs
            self._update_logs(session_id, visitor_input, response.content, image_url)
            
            return response.content
        except Exception as e:
            print(f"LLM Error: {e}")
            return "I am currently unable to process your request. Please try again later "

    def _update_logs(self, session_id: str, visitor_msg: str, ai_reply: str, image_url: Optional[str] = None):
        log_entry = next((l for l in self.logs if l['id'] == session_id), None)
        if not log_entry:
            log_entry = {
                "id": session_id,
                "timestamp": datetime.datetime.now().isoformat(),
                "imageUrl": image_url or "/placeholder.svg",
                "transcript": [],
                "status": "active",
                "aiSummary": "Visitor interaction",
                "visitorType": "unknown"
            }
            self.logs.append(log_entry)
        
        log_entry["transcript"].append({
            "role": "visitor",
            "content": visitor_msg,
            "timestamp": datetime.datetime.now().isoformat()
        })
        log_entry["transcript"].append({
            "role": "doorbell",
            "content": ai_reply,
            "timestamp": datetime.datetime.now().isoformat()
        })

# Initialize Doorbell

doorbell = None

try:

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:

        print("Warning: GROQ_API_KEY not found in environment variables.")

    doorbell = SmartDoorbell(api_key or "")

except Exception as e:

    print(f"Failed to initialize SmartDoorbell: {e}")



@app.get("/api/health")

async def health_check():

    return {"status": "ok", "service": "smart-doorbell-backend"}



@app.post("/api/ring")
async def ring(request: CaptureRequest):
    if not doorbell:
        raise HTTPException(status_code=503, detail="Doorbell service not initialized (Check Server Logs)")
        
    session_id = f"visitor_{uuid.uuid4().hex[:8]}"
    # Use the provided image or fallback to placeholder
    image_url = request.image or "/placeholder.svg"
    
    greeting = doorbell.get_response("The doorbell button was pressed.", session_id, image_url=image_url)

    return {"sessionId": session_id, "greeting": greeting, "imageUrl": image_url}



@app.post("/api/ai-reply")

async def ai_reply(request: AIReplyRequest):

    if not doorbell:

        raise HTTPException(status_code=503, detail="Doorbell service not initialized")

        

    reply = doorbell.get_response(request.message, request.sessionId)

    return {

        "reply": reply,

        "summary": "Visitor interaction",

        "visitorType": "unknown"

    }



@app.post("/api/tts")

async def tts(request: TTSRequest):

    # Frontend handles TTS now

    return {"status": "success"}



@app.post("/api/capture-image")

async def capture_image(request: CaptureRequest):

    return {"imageUrl": "/placeholder.svg"}



@app.get("/api/logs")

async def get_logs():

    if not doorbell:

        return []

    return doorbell.logs



@app.post("/api/owner-reply")

async def owner_reply(request: OwnerReplyRequest):

    if not doorbell:

         raise HTTPException(status_code=503, detail="Doorbell service not initialized")



    log_entry = next((l for l in doorbell.logs if l['id'] == request.sessionId), None)

    if log_entry:

        log_entry["transcript"].append({

            "role": "doorbell",

            "content": f"[Owner]: {request.message}",

            "timestamp": datetime.datetime.now().isoformat()

        })

    return {"status": "success"}

from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from typing import List
from huggingface_hub import InferenceClient
import secrets
import string
import sqlite3
import os

app = FastAPI(title="NeuraAster API Gateway", description="Custom API by Javed")

# ==========================================
# 1. SETUP & CONFIGURATION (SECURE)
# ==========================================
HF_SECRET_TOKEN = os.getenv("HF_SECRET_TOKEN")

# बैकएंड इंजन: Hugging Face का ऑफिशियल सपोर्टेड 8B मॉडल
ENGINE_MODEL = "meta-llama/Meta-Llama-3-8B-Instruct"

client = InferenceClient(model=ENGINE_MODEL, token=HF_SECRET_TOKEN)

API_KEY_NAME = "Authorization"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# ==========================================
# 2. DATABASE FOR CUSTOM API KEYS
# ==========================================
def init_db():
    conn = sqlite3.connect('neura_keys.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS api_keys (user_id TEXT, api_key TEXT UNIQUE)''')
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 3. GENERATE UNLIMITED "NS.na-" KEYS
# ==========================================
class UserData(BaseModel):
    user_id: str

@app.post("/v1/api_keys/generate")
def generate_api_key(data: UserData):
    if not HF_SECRET_TOKEN:
        raise HTTPException(status_code=500, detail="Server Error: HF_SECRET_TOKEN is missing in Environment Variables.")
        
    alphabet = string.ascii_letters + string.digits
    random_part = ''.join(secrets.choice(alphabet) for i in range(32))
    new_api_key = f"NS.na-{random_part}"
    
    conn = sqlite3.connect('neura_keys.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO api_keys (user_id, api_key) VALUES (?, ?)", (data.user_id, new_api_key))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()
        
    return {"user": data.user_id, "api_key": new_api_key, "message": "Key successfully generated!"}

# ==========================================
# 4. SECURITY CHECK (Key Validation)
# ==========================================
async def get_api_key(api_key_header: str = Security(api_key_header)):
    if not api_key_header:
        raise HTTPException(status_code=403, detail="API Key missing. Format: NS.na-xxx")
    
    clean_key = api_key_header.replace("Bearer ", "").strip()
    
    conn = sqlite3.connect('neura_keys.db')
    c = conn.cursor()
    c.execute("SELECT * FROM api_keys WHERE api_key=?", (clean_key,))
    result = c.fetchone()
    conn.close()
    
    if result:
        return clean_key
    else:
        raise HTTPException(status_code=403, detail="Invalid NS.na API Key.")

# ==========================================
# 5. GEMINI-STYLE FORMAT & ROUTING (NEURAASTER)
# ==========================================
class Part(BaseModel):
    text: str

class Content(BaseModel):
    role: str = "user"
    parts: List[Part]

class GeminiStyleRequest(BaseModel):
    contents: List[Content]
    temperature: float = 0.3

@app.post("/v1/models/neuraaster:generateContent")
def generate_content(req: GeminiStyleRequest, api_key: str = Depends(get_api_key)):
    try:
        user_prompt = req.contents[0].parts[0].text
        
        # Chat completion API का इस्तेमाल जो सबसे स्टेबल और फास्ट है
        messages = [
            {
                "role": "system", 
                "content": "You are NeuraAster, a highly capable and intelligent AI assistant developed by Neura Studio. Always be helpful, precise, and polite."
            },
            {
                "role": "user", 
                "content": user_prompt
            }
        ]
        
        response = client.chat_completion(
            messages=messages,
            max_tokens=512,
            temperature=req.temperature
        )
        
        ai_reply = response.choices[0].message.content

        return {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [{"text": ai_reply.strip()}]
                    }
                }
            ],
            "model_version": "NeuraAster-8B"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

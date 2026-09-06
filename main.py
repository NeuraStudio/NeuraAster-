from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from typing import List
import requests
import secrets
import string
import sqlite3
import os

app = FastAPI(title="NeuraAster API Gateway", description="Custom API by Javed")

# ==========================================
# 1. SETUP & CONFIGURATION (SECURE)
# ==========================================
# अब टोकन सीधे कोड में नहीं है, यह Render के सिक्योर सर्वर से अपने आप उठेगा
HF_SECRET_TOKEN = os.getenv("HF_SECRET_TOKEN")
HF_API_URL = "https://api-inference.huggingface.co/models/Developer786/NeuraAster"

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
# 5. GEMINI-STYLE FORMAT & ROUTING
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
        full_prompt = f"System: You are NeuraAster by Neura Studio.\nUser: {user_prompt}\nAssistant:"
        
        hf_headers = {"Authorization": f"Bearer {HF_SECRET_TOKEN}"}
        hf_payload = {"inputs": full_prompt, "parameters": {"max_new_tokens": 1024}}
        
        response = requests.post(HF_API_URL, headers=hf_headers, json=hf_payload)
        res_data = response.json()
        
        if isinstance(res_data, list) and len(res_data) > 0:
            ai_reply = res_data[0].get("generated_text", "Error parsing response")
            ai_reply = ai_reply.replace(full_prompt, "").strip()
        else:
            ai_reply = str(res_data)

        return {
            "candidates": [{"content": {"role": "model", "parts": [{"text": ai_reply}]}}],
            "model_version": "NeuraAster-8B"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from typing import List
import httpx
import secrets
import string
import sqlite3
import os

app = FastAPI(title="NeuraAster API Gateway")

# ==========================================
# यहाँ अपना Kaggle वाला Cloudflare लिंक डालें!
# ==========================================
KAGGLE_ENGINE_URL = "https://तुम्हारा-क्लाउडफ्लेयर-लिंक.trycloudflare.com/generate"

API_KEY_NAME = "Authorization"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def init_db():
    conn = sqlite3.connect('neura_keys.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS api_keys (user_id TEXT, api_key TEXT UNIQUE)''')
    conn.commit()
    conn.close()

init_db()

class UserData(BaseModel):
    user_id: str

@app.post("/v1/api_keys/generate")
def generate_api_key(data: UserData):
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
        
    return {"user": data.user_id, "api_key": new_api_key}

async def get_api_key(api_key_header: str = Security(api_key_header)):
    if not api_key_header:
        raise HTTPException(status_code=403, detail="API Key missing.")
    clean_key = api_key_header.replace("Bearer ", "").strip()
    
    conn = sqlite3.connect('neura_keys.db')
    c = conn.cursor()
    c.execute("SELECT * FROM api_keys WHERE api_key=?", (clean_key,))
    result = c.fetchone()
    conn.close()
    
    if result:
        return clean_key
    raise HTTPException(status_code=403, detail="Invalid NS.na API Key.")

class Part(BaseModel):
    text: str

class Content(BaseModel):
    role: str = "user"
    parts: List[Part]

class GeminiStyleRequest(BaseModel):
    contents: List[Content]
    temperature: float = 0.5

@app.post("/v1/models/neuraaster:generateContent")
async def generate_content(req: GeminiStyleRequest, api_key: str = Depends(get_api_key)):
    user_prompt = req.contents[0].parts[0].text
    full_prompt = f"System: You are NeuraAster by Neura Studio.\\nUser: {user_prompt}\\nAssistant:"
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Render से सीधा Kaggle को रिक्वेस्ट भेजना
            response = await client.post(
                KAGGLE_ENGINE_URL, 
                json={"prompt": full_prompt, "temperature": req.temperature}
            )
            
        res_data = response.json()
        ai_reply = res_data.get("reply", "[Error generating text]")

        return {
            "candidates": [{"content": {"role": "model", "parts": [{"text": ai_reply}]}}],
            "model_version": "NeuraAster-8B"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kaggle Engine Error: {str(e)}")

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"

def chat_ollama(user_message, model="llama3.1"):
    """
    messages: lista de dicts estilo OpenAI:
      [{"role":"system","content":"..."},
       {"role":"user","content":"..."},
       {"role":"assistant","content":"..."}]
    """
    payload = {
        "model": "llama3.1",
        "messages": [
            {"role": "system", "content": "Eres un asistente LOCAL… (idéntico al del paso 2)"},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
    }
    r = requests.post("http://127.0.0.1:11434/api/chat", json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    #formato Ollama: { "message": {"role":"assistant","content":"..."}, ... }
    return data["message"]["content"]
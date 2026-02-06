import json
from database.connection import db

MEMORY_EXTRACTION_PROMPT = """
You are a Memory Extraction AI. Your job is to identify "long-term facts" from a conversation.
Extract: 
1. Preferences (e.g., "I like blue")
2. Facts (e.g., "My sister is Sarah")
3. Constraints (e.g., "Don't call me after 5 PM")
4. Commitments (e.g., "I promised to send the report")

Return ONLY a valid JSON list of objects. If no new information is found, return [].

Format:
[
  {{
    "type": "preference | fact | constraint | commitment",
    "key": "short_identifier",
    "value": "the_actual_info",
    "confidence": 0.0 to 1.0
  }}
]

Conversation:
{text}
"""

class MemoryEngine:
    async def extract_and_store(self, session_id: str, text: str):
        # 1. Ask Gemini to extract facts
        prompt = MEMORY_EXTRACTION_PROMPT.format(text=text)
        response = db.llm.invoke(prompt)
        
        # 2. Clean and Parse JSON
        try:
            # Handle cases where LLM adds ```json tags
            cleaned_content = response.content.replace("```json", "").replace("```", "").strip()
            memories = json.loads(cleaned_content)
            
            # 3. Save each memory to DB
            results = []
            for mem in memories:
                res = await db.add_structured_memory(
                    session_id=session_id,
                    memory_type=mem['type'],
                    content={"key": mem['key'], "value": mem['value']},
                    confidence=mem['confidence']
                )
                results.append(res)
            
            return results
        except Exception as e:
            print(f"Extraction Error: {e}")
            return []

memory_engine = MemoryEngine()
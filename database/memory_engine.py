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

class ChatEngine:
    async def generate_response(self, session_id: str, user_input: str):
        # 1. Retrieve Relevant Memories
        memories = await db.get_relevant_memories(session_id, user_input)
        
        # 2. Format memories for the prompt
        memory_context = ""
        if memories:
            memory_context = "Relevant information from previous turns:\n"
            for m in memories:
                memory_context += f"- {m['memory_type']}: {m['content']['key']} is {m['content']['value']}\n"

        # 3. Construct System Prompt
        system_prompt = f"""
        You are a helpful AI assistant with long-term memory. 
        Use the following retrieved memories to personalize your response. 
        If the memories are not relevant to the current question, ignore them.
        
        {memory_context}
        """

        # 4. Get response from Gemini
        # We include the system prompt as a SystemMessage or part of the context
        messages = [
            ("system", system_prompt),
            ("human", user_input)
        ]
        
        response = db.llm.invoke(messages)
        return response.content, memories

memory_engine = MemoryEngine()
chat_engine = ChatEngine()
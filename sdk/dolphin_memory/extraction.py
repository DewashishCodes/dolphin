"""
Triple Extraction
==================
Extracts (Subject, Predicate, Object) triples from text using local or cloud LLMs.
Primary: Ollama (local, saves tokens). Fallback: Cloud LLM (Gemini/OpenAI).
"""

import json
import re
import logging
from typing import List, Dict, Any

from dolphin_memory.config import DolphinConfig

logger = logging.getLogger("dolphin.extraction")


class TripleExtractor:
    """Extracts knowledge graph triples from natural language text."""

    def __init__(self, config: DolphinConfig):
        self._config = config

    def extract(self, text: str) -> List[Dict[str, str]]:
        """
        Extract triples from text. Uses local Ollama by default.
        """
        logger.debug(f"Starting extraction for text: {text[:50]}...")
        if self._config.extraction_provider == "ollama":
            triples = self._extract_local(text)
            if not triples and self._config.cloud_api_key:
                logger.info("Local extraction empty, trying cloud fallback...")
                triples = self._extract_cloud(text)
        else:
            triples = self._extract_cloud(text)
            if not triples:
                logger.info("Cloud extraction empty, trying local fallback...")
                triples = self._extract_local(text)

        logger.info(f"Extracted {len(triples)} triples")
        return triples

    def _extract_local(self, text: str) -> List[Dict[str, str]]:
        """Extract triples using local Ollama (Llama 3.2)."""
        try:
            import ollama

            response = ollama.chat(
                model=self._config.ollama_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a Knowledge Graph extraction engine. "
                            "Extract factual relationships from the user's message.\n"
                            'Return ONLY a valid JSON array. Format: '
                            '[{"s": "Subject", "p": "RELATIONSHIP", "o": "Object", "ol": "Label"}]\n'
                            "Rules:\n"
                            "- Use 'User' as subject when the speaker talks about themselves\n"
                            "- Relationships: UPPER_SNAKE_CASE (LIVES_IN, WORKS_AT, LIKES, etc.)\n"
                            "- Labels: Person, City, Country, Skill, Language, Company, Role, Concept, Entity\n"
                            "- Only extract concrete facts. Skip greetings and filler.\n"
                            "- If no facts found, return []"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Extract facts from: '{text}'",
                    },
                ],
                format="json",
                options={"temperature": 0},
            )

            raw = response["message"]["content"]
            return self._parse(raw)
        except ImportError:
            logger.error(
                "Ollama package not installed. Run: pip install ollama\n"
                "Then install Ollama: https://ollama.com\n"
                "Then pull the model: ollama pull llama3.2"
            )
            return []
        except Exception as e:
            logger.warning(f"Local extraction failed (is Ollama running?): {e}")
            return []

    def _extract_cloud(self, text: str) -> List[Dict[str, str]]:
        """Extract triples using cloud LLM (Gemini/OpenAI)."""
        try:
            provider = self._config.extraction_provider
            api_key = self._config.cloud_api_key

            if not api_key:
                logger.warning("No cloud API key configured for extraction")
                return []

            if provider == "gemini":
                from langchain_google_genai import ChatGoogleGenerativeAI
                llm = ChatGoogleGenerativeAI(
                    model="gemini-2.5-flash",
                    temperature=0,
                    google_api_key=api_key,
                )
            elif provider == "openai":
                from langchain_openai import ChatOpenAI
                llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=api_key)
            else:
                logger.warning(f"Unknown cloud provider: {provider}")
                return []

            prompt = (
                "You are a Knowledge Graph extraction engine. "
                "Extract factual relationships from the user's message.\n\n"
                'Return ONLY a valid JSON array. Format: '
                '[{"s": "Subject", "p": "RELATIONSHIP", "o": "Object", "ol": "Label"}]\n\n'
                "Rules:\n"
                "- Use 'User' as subject when the speaker talks about themselves\n"
                "- Relationships: UPPER_SNAKE_CASE\n"
                "- Labels: Person, City, Country, Skill, Language, Company, Role, Concept, Entity\n"
                "- Only extract concrete facts. Skip filler.\n"
                "- If no facts found, return []\n\n"
                f'User message: "{text}"'
            )

            res = llm.invoke(prompt)
            content = res.content if hasattr(res, "content") else str(res)

            # Handle Gemini list wrapping
            if isinstance(content, list) and len(content) > 0:
                if isinstance(content[0], dict) and "text" in content[0]:
                    content = content[0]["text"]
                else:
                    content = str(content[0])

            return self._parse(content)
        except Exception as e:
            logger.warning(f"Cloud extraction failed: {e}")
            return []

    def _parse(self, raw_text: str) -> List[Dict[str, str]]:
        """Parse LLM output into a clean list of triple dicts."""
        try:
            # Find the JSON array in the response
            match = re.search(r"\[.*\]", raw_text, re.DOTALL)
            clean = match.group(0) if match else raw_text

            # Fix common LLM hallucinations
            clean = clean.replace('""', '"').replace('\\"', '"')

            data = json.loads(clean)

            if isinstance(data, dict):
                data = [data]

            # Validate and normalize
            results = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                s = item.get("s") or item.get("subject") or "User"
                p = item.get("p") or item.get("predicate") or "RELATED_TO"
                o = item.get("o") or item.get("object")
                ol = item.get("ol") or item.get("label") or "Entity"
                if o:
                    results.append({
                        "s": str(s),
                        "p": str(p).upper().replace(" ", "_"),
                        "o": str(o),
                        "ol": str(ol),
                    })
            return results
        except (json.JSONDecodeError, AttributeError) as e:
            logger.debug(f"JSON parse failed: {e}. Raw: {raw_text[:200]}")
            return []

"""
Triple Extraction
==================
Extracts (Subject, Predicate, Object) triples from text using local or cloud LLMs,
and distills agent conversations into durable facts worth remembering.
Primary: Ollama (local, saves tokens). Fallback: Cloud LLM (Gemini/OpenAI).
"""

import json
import re
import logging
from typing import List, Dict, Optional

from dolphin_memory.config import DolphinConfig

logger = logging.getLogger("dolphin.extraction")

_TRIPLE_FORMAT = (
    'Return ONLY a valid JSON array. Format: '
    '[{"s": "Subject", "p": "RELATIONSHIP", "o": "Object", "ol": "Label"}]\n'
)

# Personal facts about the person talking to an assistant
PERSONAL_PROMPT = (
    "You are a Knowledge Graph extraction engine. "
    "Extract factual relationships from the user's message.\n"
    + _TRIPLE_FORMAT +
    "Rules:\n"
    "- Use 'User' as subject when the speaker talks about themselves\n"
    "- Relationships: UPPER_SNAKE_CASE (LIVES_IN, WORKS_AT, LIKES, etc.)\n"
    "- Labels: Person, City, Country, Skill, Language, Company, Role, Concept, Entity\n"
    "- Only extract concrete facts. Skip greetings and filler.\n"
    "- If no facts found, return []"
)

# Project knowledge recorded by coding agents
AGENT_PROMPT = (
    "You are a Knowledge Graph extraction engine for a software project's memory. "
    "Extract factual relationships from the statement.\n"
    + _TRIPLE_FORMAT +
    "Rules:\n"
    "- The subject is the thing the statement is about; the object is what it is "
    "related to. Both are concrete named things: files, modules, services, tools, "
    "commands, libraries, people, decisions\n"
    "- Copy names exactly as written. Never split a file path or a command\n"
    "- Use 'User' as subject only for the developer's own preferences\n"
    "- Relationships: UPPER_SNAKE_CASE (USES, DOES_NOT_USE, DEPENDS_ON, DEFINED_IN, "
    "DEPLOYED_WITH, RUN_WITH, REPLACED_BY, OWNED_BY, PREFERS, AVOIDS, CAUSED_BY, "
    "FIXED_IN, etc.)\n"
    "- Labels: File, Module, Service, Tool, Command, Library, Person, Decision, "
    "Concept, Entity\n"
    "- Only extract concrete facts. Skip filler.\n"
    "- If no facts found, return []\n"
    "Examples:\n"
    "Statement: The job queue uses a Postgres table instead of Redis.\n"
    '[{"s": "job queue", "p": "USES", "o": "Postgres", "ol": "Tool"}, '
    '{"s": "job queue", "p": "DOES_NOT_USE", "o": "Redis", "ol": "Tool"}]\n'
    "Statement: The developer prefers pnpm over npm.\n"
    '[{"s": "User", "p": "PREFERS", "o": "pnpm", "ol": "Tool"}, '
    '{"s": "User", "p": "AVOIDS", "o": "npm", "ol": "Tool"}]\n'
    "Statement: The RateLimiter class is defined in api/limits.py and is built with "
    "`make api`.\n"
    '[{"s": "RateLimiter", "p": "DEFINED_IN", "o": "api/limits.py", "ol": "File"}, '
    '{"s": "RateLimiter", "p": "BUILT_WITH", "o": "make api", "ol": "Command"}]'
)

DISTILL_PROMPT = (
    "You maintain the long-term memory of a coding agent. Below is one exchange "
    "between a developer and the agent. List the facts a FUTURE session on this "
    "project would need and could not easily rediscover from the code.\n"
    "Keep: decisions and their reasons (including what was rejected), conventions, "
    "the developer's preferences and corrections, gotchas, root causes of bugs, "
    "how to build/test/deploy.\n"
    "Drop: what was done step by step, explanations of what existing code does, "
    "pleasantries, temporary state such as test results, secrets or credentials.\n"
    "Each fact is ONE complete, self-contained sentence that names the things it is "
    "about. Never output a bare file name or a fragment.\n"
    'Return ONLY JSON: {"facts": ["...", "..."]} with at most 5 facts. If the '
    'exchange is only routine work, an explanation or small talk, return {"facts": []}.\n'
    "Examples:\n"
    "Exchange: Developer: Should the job queue use Redis?\n"
    "Agent: No. We use a Postgres table with SKIP LOCKED for the job queue instead "
    "of Redis, so there is one less service to run.\n"
    '{"facts": ["The job queue uses a Postgres table with SKIP LOCKED instead of '
    'Redis, to avoid running another service."]}\n'
    "Exchange: Developer: fix the typo in the README\n"
    "Agent: Fixed 'recieve' to 'receive' in README.md.\n"
    '{"facts": []}\n'
    "Exchange: Developer: Why did CI fail?\n"
    "Agent: CI ran Node 18 but the lockfile needs Node 20. I pinned node-version to "
    "20 in .github/workflows/ci.yml. Note: CI must run `npm ci`, never `npm install`.\n"
    '{"facts": ["CI needs Node 20 because the lockfile is incompatible with Node 18; '
    'the version is pinned in .github/workflows/ci.yml.", "CI must run `npm ci`, '
    'never `npm install`."]}\n'
    "Exchange: Developer: Stop adding type: ignore comments. Fix the types.\n"
    "Agent: Understood, I removed them and fixed the annotations.\n"
    '{"facts": ["The developer does not want `# type: ignore` comments; type errors '
    'must be fixed properly."]}'
)

# Ollama constrains its output to these schemas, so small models cannot wander
_TRIPLE_SCHEMA = {
    "type": "object",
    "properties": {
        "triples": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "s": {"type": "string"},
                    "p": {"type": "string"},
                    "o": {"type": "string"},
                    "ol": {"type": "string"},
                },
                "required": ["s", "p", "o", "ol"],
            },
        }
    },
    "required": ["triples"],
}
_FACTS_SCHEMA = {
    "type": "object",
    "properties": {"facts": {"type": "array", "items": {"type": "string"}}},
    "required": ["facts"],
}

# A fact shorter than this is a fragment ("src/cache.py"), not a sentence
MIN_FACT_WORDS = 4

# Never store text that looks like a credential
_SECRET_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"
    r"xox[abpr]-[A-Za-z0-9-]{10,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"(?i:password|passwd|secret|api[_-]?key|token)\s*[:=]\s*\S{6,})"
)


def looks_like_secret(text: str) -> bool:
    """True if the text appears to contain a credential."""
    return bool(_SECRET_PATTERN.search(text))


class TripleExtractor:
    """Extracts knowledge graph triples from natural language text."""

    def __init__(self, config: DolphinConfig):
        self._config = config

    def extract(self, text: str) -> List[Dict[str, str]]:
        """
        Extract triples from text. Uses local Ollama by default.
        """
        logger.debug(f"Starting extraction for text: {text[:50]}...")
        system = AGENT_PROMPT if self._config.extraction_profile == "agent" else PERSONAL_PROMPT
        raw = self._complete(
            system, f"Statement: {text}", parses=self._parse, schema=_TRIPLE_SCHEMA
        )
        triples = self._parse(raw) if raw else []

        logger.info(f"Extracted {len(triples)} triples")
        return triples

    def distill(self, text: str) -> List[str]:
        """
        Reduce an agent exchange to the durable facts worth remembering.
        Returns [] when nothing is worth keeping or no LLM is available.
        """
        raw = self._complete(
            DISTILL_PROMPT, f"Exchange: {text}", parses=self._parse_facts,
            schema=_FACTS_SCHEMA,
        )
        facts = self._parse_facts(raw) if raw else []
        facts = [f for f in facts if not looks_like_secret(f)]
        logger.info(f"Distilled {len(facts)} facts")
        return facts

    # -------------------------------------------------------------------------
    # LLM access
    # -------------------------------------------------------------------------

    def _complete(self, system: str, user: str, parses, schema=None) -> Optional[str]:
        """
        Run the prompt on the configured provider. If its answer is unusable
        (`parses` returns nothing), try the other one. `schema` is a JSON schema
        the local model's output is constrained to.
        """
        if self._config.extraction_provider == "ollama":
            raw = self._complete_local(system, user, schema)
            if not (raw and parses(raw)) and self._config.cloud_api_key:
                logger.info("Local extraction empty, trying cloud fallback...")
                raw = self._complete_cloud(system, user)
        else:
            raw = self._complete_cloud(system, user)
            if not (raw and parses(raw)):
                logger.info("Cloud extraction empty, trying local fallback...")
                raw = self._complete_local(system, user, schema)
        return raw

    def _complete_local(self, system: str, user: str, schema=None) -> Optional[str]:
        """Run the prompt on local Ollama (Llama 3.2)."""
        try:
            import ollama

            response = ollama.chat(
                model=self._config.ollama_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                format=schema or "json",
                options={"temperature": 0},
            )
            return response["message"]["content"]
        except ImportError:
            logger.error(
                "Ollama package not installed. Run: pip install ollama\n"
                "Then install Ollama: https://ollama.com\n"
                "Then pull the model: ollama pull llama3.2"
            )
            return None
        except Exception as e:
            logger.warning(f"Local extraction failed (is Ollama running?): {e}")
            return None

    def _complete_cloud(self, system: str, user: str) -> Optional[str]:
        """Run the prompt on a cloud LLM (Gemini/OpenAI)."""
        try:
            provider = self._config.extraction_provider
            api_key = self._config.cloud_api_key

            if not api_key:
                logger.warning("No cloud API key configured for extraction")
                return None

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
                return None

            res = llm.invoke(f"{system}\n\n{user}")
            content = res.content if hasattr(res, "content") else str(res)

            # Handle Gemini list wrapping
            if isinstance(content, list) and len(content) > 0:
                if isinstance(content[0], dict) and "text" in content[0]:
                    content = content[0]["text"]
                else:
                    content = str(content[0])

            return content
        except Exception as e:
            logger.warning(f"Cloud extraction failed: {e}")
            return None

    # -------------------------------------------------------------------------
    # Parsing
    # -------------------------------------------------------------------------

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

    def _parse_facts(self, raw_text: str) -> List[str]:
        """Parse LLM output into a list of fact strings."""
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", raw_text, re.DOTALL)
            if not match:
                return []
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                return []

        # Ollama's JSON mode often wraps the array: {"facts": [...]}
        if isinstance(data, dict):
            data = next((v for v in data.values() if isinstance(v, list)), [])
        if not isinstance(data, list):
            return []
        return [
            f.strip() for f in data
            if isinstance(f, str) and len(f.split()) >= MIN_FACT_WORDS
        ][:5]

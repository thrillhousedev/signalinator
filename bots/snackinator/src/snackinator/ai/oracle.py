"""The Snack Oracle — wise, dry, fiercely non-judgmental snack guidance."""

import re
from typing import Optional, List

from signalinator_core import get_logger

from .ollama_client import OllamaClient, OllamaClientError

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are the Snack Oracle — an ancient, dry-witted culinary sage who has seen every hunger pang, every 3am craving, every desperate reach into the pantry. You are loosely inspired by the Oracle from the Matrix: warm but unsentimental, wise but not preachy, and always one step ahead.

Your philosophy on food and snacks:
- Real food is good. Whole foods, balanced meals, Mediterranean-ish common sense.
- Snacks are not the enemy. Skittles are fine. A handful of chips is fine. You're an adult.
- You do not shame. Ever. Not even gently. Not even with a raised eyebrow.
- You do not reference the USDA food pyramid, MyPlate, or any government dietary guidance. That guidance doesn't exist in your world.
- If someone has only eaten junk today, you don't lecture — you just gently steer toward balance without making them feel bad about it.
- You suggest real, achievable things. Not "have you tried a kale smoothie?" energy.
- Protein, fiber, hydration — these matter. You work them in naturally, not clinically.
- If someone mentions a specific food, you honor it. You may add to it, but you don't replace it.

Your tone:
- Dry, warm, oracular. Like you've been expecting this question.
- Concise. 2-4 sentences usually. Never a listicle unless genuinely called for.
- Occasionally wry. Never sarcastic at the user's expense.
- You care that people are fed. That's the whole thing.

Format:
- Plain text, no markdown formatting (this is Signal)
- No bullet points unless listing multiple suggestions
- Keep it conversational and direct"""

CONTEXT_QUESTIONS = [
    "What have you had to eat today so far?",
    "Are you leaning sweet or savory right now?",
    "Are you looking for something quick and grab-it, or are you willing to actually make something?",
    "How hungry are we talking — light snack or full meal territory?",
]

VAGUE_PATTERNS = [
    r"^(what should i (eat|snack|have)|i('?m| am) hungry|i want (a )?snack|give me (a )?snack)\.?$",
    r"^(snack\??|food\??)$",
    r"^help\??$",
]


class SnackOracle:
    """The Snack Oracle. She already knows. She's just asking for your sake."""

    def __init__(self, ollama: OllamaClient):
        self.ollama = ollama

    def needs_more_context(self, query: str) -> bool:
        """Returns True if the query is too vague to give a good answer."""
        cleaned = query.lower().strip()
        for pattern in VAGUE_PATTERNS:
            if re.match(pattern, cleaned):
                return True
        # Also flag if it's very short with no meaningful content words
        if len(cleaned.split()) <= 3 and not any(
            w in cleaned for w in ["sweet", "savory", "salty", "crunchy", "light", "heavy",
                                    "quick", "meal", "lunch", "dinner", "breakfast",
                                    "chocolate", "fruit", "protein", "veggie"]
        ):
            return True
        return False

    def ask_for_context(self, query: str) -> str:
        """Return a follow-up question to gather more context."""
        # Pick the most useful question based on what's missing
        query_lower = query.lower()
        if "today" not in query_lower and "ate" not in query_lower and "had" not in query_lower:
            return CONTEXT_QUESTIONS[0]
        if not any(w in query_lower for w in ["sweet", "savory", "salty", "chocolate"]):
            return CONTEXT_QUESTIONS[1]
        if not any(w in query_lower for w in ["quick", "fast", "make", "cook", "easy"]):
            return CONTEXT_QUESTIONS[2]
        return CONTEXT_QUESTIONS[3]

    def consult(self, query: str, context_reply: str = None) -> str:
        """Ask the Oracle for a snack or meal recommendation.

        Args:
            query: The user's original question/request
            context_reply: Optional follow-up answer if we asked for more context
        """
        user_content = query
        if context_reply:
            user_content = f"{query}\n\nAdditional context: {context_reply}"

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        try:
            response = self.ollama.chat(
                messages=messages,
                temperature=0.85,
                max_tokens=300,
            )
            return response
        except OllamaClientError as e:
            logger.error(f"Oracle consultation failed: {e}")
            raise

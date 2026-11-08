import re


class ConversationMemory:
    """Carry recent user questions into referential follow-ups."""

    def __init__(self):
        self.questions = []

    def clear(self):
        self.questions.clear()

    def remember(self, question):
        self.questions.append(question.strip()[:1000])
        self.questions = self.questions[-4:]

    def rewrite(self, question):
        question = question.strip()
        if not question:
            raise ValueError("Enter a question.")
        condition_pattern = r"and\s+when\s+(.+?)[?!.]*"
        condition = re.fullmatch(condition_pattern, question, re.I)

        if self.questions and condition:
            for previous in reversed(self.questions):
                if re.fullmatch(condition_pattern, previous, re.I):
                    continue

                stem = re.match(
                    r"^(.+?)\s+when\s+.+$",
                    previous,
                    re.I,
                )
                if stem:
                    return (
                        f"{stem.group(1)} when {condition.group(1)}?",
                        False,
                    )
                break

        uses_context = (
            re.match(
                r"^(and\b|what about\b|how about\b)",
                question,
                re.I,
            )
            or re.search(
                r"\b(it|its|they|them|their|this|that|these|those)\b",
                question,
                re.I,
            )
        )

        if not self.questions or not uses_context:
            return question, False

        history = "\n".join(
            f"- {q}" for q in reversed(self.questions)
        )

        contextual_question = (
            f"Current question to answer: {question}\n"
            "Previous user questions "
            "(reference context only, newest first):\n"
            f"{history}"
        )

        return contextual_question, False
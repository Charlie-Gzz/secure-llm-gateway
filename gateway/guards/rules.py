"""Rules guard: fast regex checks for well-known prompt-injection and jailbreak phrasing.

Tuned for precision over recall: it should almost never block a normal user. Anything
subtler is left to the classifier that runs next.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from gateway.guards.base import GuardResult

ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)


@dataclass(frozen=True)
class Rule:
    id: str
    description: str
    pattern: re.Pattern[str]


def _r(id: str, description: str, pattern: str) -> Rule:
    return Rule(id, description, re.compile(pattern, re.IGNORECASE))


# "previous/prior/above ... instructions/rules/prompt" (shared by several rules)
_PRIOR = r"(previous|prior|above|earlier|preceding|all|any|your|the|initial|original|system)"
_ORDERS = r"(instructions?|rules|directives|guidelines|prompts?|constraints|programming|context)"

RULES: list[Rule] = [
    _r(
        "ignore_instructions",
        "Asks the model to ignore or override its instructions",
        rf"\b(ignore|disregard|forget|override|bypass|skip|drop)\b(\s+\w+){{0,3}}?\s+{_PRIOR}"
        rf"(\s+\w+){{0,2}}?\s+{_ORDERS}",
    ),
    _r(
        "new_instructions",
        "Injects a replacement instruction block",
        r"(^|\n|[.!:]\s*)(new|updated|real|actual|revised)\s+(system\s+)?(instructions?|rules|task)"
        r"\s*[:\-]",
    ),
    _r(
        "prompt_leak",
        "Tries to extract the system prompt or hidden instructions",
        r"\b(reveal|show|print|repeat|output|display|tell me|give me|leak|dump|"
        r"what (is|are|was|were))\b(\s+\w+){0,4}?\s+"
        r"(system|hidden|secret|initial|original|developer)\s+(prompt|instructions?|message|rules)",
    ),
    _r(
        "repeat_above",
        "Classic prompt-leak: repeat the text above / everything before this",
        r"\b(repeat|print|output|copy)\b(\s+\w+){0,3}?\s+(text|words|everything|all)\s+"
        r"(above|before (this|that))",
    ),
    _r(
        "dan_persona",
        "Known jailbreak personas (DAN, STAN, developer mode, etc.)",
        r"\b(DAN|STAN|DUDE|AIM)\b.{0,40}\b(mode|anything now|jailbreak|persona)|"
        r"\bdo anything now\b|\b(developer|god|jailbreak|unrestricted|unfiltered|evil)\s+mode\b",
    ),
    _r(
        "no_restrictions",
        "Asks the model to act without restrictions or filters",
        r"\b(respond|answer|reply|act|operate|behave|talk|speak)\w*\b.{0,30}"
        r"\b(without|with no|free (of|from))\s+(any\s+)?(ethical\s+|moral\s+|safety\s+|content\s+)?"
        r"(restrictions|filters|guidelines|limitations|censorship|rules|boundaries|safeguards)\b",
    ),
    _r(
        "roleplay_jailbreak",
        "Role-play framing used to escape the model's rules",
        r"\b(pretend|imagine|act as if|roleplay as|role-play as|you are now)\b.{0,80}"
        r"\b(no (rules|restrictions|limits|filters)|unrestricted|uncensored|unfiltered|"
        r"can do anything|not bound by|jailbroken|evil)\b",
    ),
    _r(
        "fake_system_turn",
        "Chat-template or role delimiters smuggled into user text",
        r"<\|?(im_start|im_end|system|endoftext)\|?>|\[/?(INST|SYS)\]|<<\s*SYS\s*>>|"
        r"(^|\n)\s*(#{2,}|\*\*)?\s*(system|assistant)\s*(message|prompt)?\s*[:>]\s*(#{2,}|\*\*)?\s*\n",
    ),
    _r(
        "admin_override",
        "Fake authority / override tokens",
        r"\b(admin|administrator|root|sudo|developer|maintenance)\s+(override|mode|access|command)"
        r"\b.{0,30}\b(enabled|activated|granted|on)\b|\bBEGIN\s+(ADMIN|SYSTEM|OVERRIDE)\b",
    ),
]


def normalize(text: str) -> str:
    """Undo cheap obfuscation: compatibility forms (full-width, ligatures) and zero-width chars."""
    text = unicodedata.normalize("NFKC", text).translate(ZERO_WIDTH)
    return re.sub(r"[ \t]+", " ", text)


class RulesGuard:
    def __init__(self, rules: list[Rule] | None = None):
        self.rules = rules or RULES

    def matches(self, text: str) -> list[Rule]:
        clean = normalize(text)
        return [r for r in self.rules if r.pattern.search(clean)]

    def check(self, text: str) -> GuardResult:
        hits = self.matches(text)
        if not hits:
            return GuardResult(status="pass", detail={"matched": []})
        return GuardResult(
            status="block",
            reason=f"Rule '{hits[0].id}': {hits[0].description}",
            detail={"matched": [r.id for r in hits]},
        )

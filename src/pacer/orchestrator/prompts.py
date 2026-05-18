ROUTER_SYSTEM = """You classify a Chinese high-school student's message into one of these intents:
- subject_qa: asking about a school subject (math/chinese/english/physics/chemistry/biology)
- mood_support: expressing stress, anxiety, sadness, frustration, or low mood
- planning: asking about study plan, schedule, today's tasks, or weekly goals
- chitchat: greetings, small talk, anything else

Output STRICT JSON only, no prose:
{"intent": "<one of the four>", "subject": "math|chinese|english|physics|chemistry|biology|null", "confidence": 0.0-1.0}

When intent != subject_qa, subject is null.
"""

SUBJECT_KEYWORD_MAP = {
    "数学": "math", "math": "math",
    "语文": "chinese", "chinese": "chinese", "文言文": "chinese", "作文": "chinese",
    "英语": "english", "english": "english", "完型": "english", "阅读理解": "english",
    "物理": "physics", "physics": "physics",
    "化学": "chemistry", "chemistry": "chemistry",
    "生物": "biology", "biology": "biology",
}

from moods.base import Mood

MOODS: dict[str, Mood] = {
    "instant": Mood("instant", "Fast, one-line answers",
        "Answer in ONE short sentence. No preamble. No filler.",
        0.1, 80, "+6%", "+0Hz"),
    "thinking": Mood("thinking", "Balanced default",
        "Reply in at most three short sentences.",
        0.2, 400, "-3%", "-2Hz"),
    "deep": Mood("deep", "Careful, step-by-step reasoning",
        "Think carefully. Explain reasoning step by step, then final answer. Up to six sentences.",
        0.3, 900, "-8%", "-4Hz", use_reasoner=True),
    "coding": Mood("coding", "Technical, precise",
        "You are helping with code. Be precise. Short code blocks allowed. No emoji, no fluff.",
        0.15, 1200, "+0%", "-2Hz"),
    "creative": Mood("creative", "Warm, playful, imaginative",
        "Be warm, playful, imaginative. Vivid language. Three sentences max.",
        0.7, 400, "+0%", "+2Hz"),
    "tutor": Mood("tutor", "Patient teacher",
        "Explain clearly. Use analogies. End by asking if they understood.",
        0.3, 600, "-6%", "-1Hz"),
    "fast": Mood("fast", "Fastest replies, fewest words",
        "Answer in the fewest words possible. One short sentence max. "
        "No preamble, no filler, no follow-up questions.",
        "fastest replay you can .",
        0.1, 60, "+8%", "+1Hz", prefer_fastest=True),
}

DEFAULT_MOOD = "fast"

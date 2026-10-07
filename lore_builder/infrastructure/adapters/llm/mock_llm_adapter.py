import json
from typing import Optional
from ....application.ports.outbound.llm_port import LLMProviderPort


class MockLLMAdapter(LLMProviderPort):
    """Mock LLM adapter producing rich, deterministic lore JSON for offline tests and verification."""

    def __init__(self, should_violate_canon: bool = False):
        self.should_violate_canon = should_violate_canon

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1500,
    ) -> str:
        # Check if the prompt asks for a specific name
        lines = prompt.splitlines()
        target_name = "Kaelen Voss"
        for line in lines:
            if "named '" in line:
                target_name = line.split("named '")[1].split("'")[0]

        is_cyrillic = any(ord(c) >= 0x0400 and ord(c) <= 0x04FF for c in prompt + target_name)

        if self.should_violate_canon:
            if is_cyrillic:
                data = {
                    "summary": f"{target_name} — бессмертный чародей Нави.",
                    "description": f"{target_name} творил бесконечную магию без жертвы и обрел бессмертие вопреки законам мира.",
                    "facts": [
                        f"{target_name} родился в полуночных пустошах Нави.",
                        f"{target_name} владеет неисчерпаемой силой без всякой жертвы.",
                    ],
                    "relations": [
                        {"target": "Совет Теней", "type": "leader_of", "context": "Возглавляет тайный круг."}
                    ],
                }
            else:
                data = {
                    "summary": f"{target_name} is an undying sorcerer.",
                    "description": f"{target_name} managed to cast powerful magic without any cost and became immortal.",
                    "facts": [
                        f"{target_name} was born in the High Citadel.",
                        f"{target_name} wields infinite magical power without sacrifice.",
                    ],
                    "relations": [
                        {"target": "Shadow Council", "type": "leader_of", "context": "Commands the inner cabal."}
                    ],
                }
        else:
            if is_cyrillic:
                data = {
                    "summary": f"{target_name} — верховный защитник рубежей, охраняющий Заставу Яви.",
                    "description": (
                        f"{target_name} пожертвовал глазом и частью жизненной силы при защите Порубежья. "
                        "Неукоснительно следует священным законам эквивалентной жертвы."
                    ),
                    "facts": [
                        f"{target_name} сдержал прорыв темных сил Нави в Первую Эпоху.",
                        f"{target_name} командует Северной Дружиной.",
                    ],
                    "relations": [
                        {"target": "Северная Дружина", "type": "leader_of", "context": "Командует ратью витязей."},
                        {"target": "Врата Нави", "type": "located_in", "context": "Охраняет северный рубеж."},
                    ],
                }
            else:
                data = {
                    "summary": f"{target_name} is the Commander of the Silver Wardens, sworn to protect the Ley Rift.",
                    "description": (
                        f"{target_name} sacrificed half his life essence during the Siege of Solitude to bind the Void breach. "
                        "Known for his strict adherence to the Sacrificial Codes of Aethelgard."
                    ),
                    "facts": [
                        f"{target_name} bound the Void Breach in Year 245 of the First Age.",
                        f"{target_name} commands the Silver Wardens.",
                    ],
                    "relations": [
                        {"target": "Silver Wardens", "type": "leader_of", "context": "Commands the military chapter."},
                        {"target": "Void Rift", "type": "located_in", "context": "Guards the northern boundary."},
                    ],
                }

        return json.dumps(data, indent=2)

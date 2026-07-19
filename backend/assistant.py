import os
from mem0 import MemoryClient
from alchemyst_ai import AlchemystAI
from openai import OpenAI

mem0_client = MemoryClient(api_key=os.environ["MEM0_API_KEY"])
alchemyst_client = AlchemystAI(api_key=os.environ["ALCHEMYST_AI_API_KEY"])

llm_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

def answer_officer_query(query: str, officer_id: str) -> str:
    memories = mem0_client.search(query, filters={"user_id": officer_id})
    memory_text = "\n".join(m["memory"] for m in memories.get("results", memories) if isinstance(m, dict))

    context_results = alchemyst_client.v1.context.search(
    query=query,
    similarity_threshold=0.5,
    minimum_similarity_threshold=0.3,
)
    context_text = "\n".join(c.content for c in getattr(context_results, "contexts", []))

    system_prompt = (
        "You are AutoSentinel's AI assistant for field officers investigating "
        "illegal construction. Use the context below to give accurate, "
        "source-backed answers.\n\n"
        f"Officer's past context:\n{memory_text}\n\n"
        f"Relevant zone/report data:\n{context_text}"
    )

    response = llm_client.chat.completions.create(
        model="anthropic/claude-sonnet-4.5",  # any OpenRouter model slug works here
        max_tokens=500,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
    )
    answer = response.choices[0].message.content

    mem0_client.add(
        [{"role": "user", "content": query}, {"role": "assistant", "content": answer}],
        user_id=officer_id,
    )
    return answer
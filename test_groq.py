"""Quick test: call Groq API directly with a payment scenario."""
from dotenv import load_dotenv
load_dotenv()
import os
from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
prompt = open("api/prompts/groq_system_prompt.txt").read()
context = (
    'Detected objects: person (85%)\n'
    'Visitor said: "the payment of the package still has to be done"\n'
    'Emotion: neutral\n'
    'Risk level: normal\n'
    'Weapon detected: No'
)

print("Sending to Groq...")
resp = client.chat.completions.create(
    model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
    messages=[
        {"role": "system", "content": prompt},
        {"role": "user", "content": context},
    ],
    max_tokens=128,
    temperature=0.2,
)
print(f"Groq reply: {resp.choices[0].message.content}")

import os
from dotenv import load_dotenv
from llama_index.llms.openrouter import OpenRouter
from llama_index.core.llms import ChatMessage

load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY", "")
model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")

client = OpenRouter(
    api_key=api_key,
    model=model,
    max_tokens=16384,
    temperature=0.7,
)

messages = [
    ChatMessage(role="system", content="You are an AI assistant that helps people find information."),
]

response = client.chat(messages)
print(response.message.content)

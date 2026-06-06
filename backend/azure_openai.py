import os
import base64
from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
      
endpoint = os.getenv("ENDPOINT_URL", "https://datascienceopenai-actualeastus2.openai.azure.com/")
deployment = os.getenv("DEPLOYMENT_NAME", "gpt-4o")
      
# Initialize Azure OpenAI client with Entra ID authentication
token_provider = get_bearer_token_provider(
    DefaultAzureCredential(),
    "https://cognitiveservices.azure.com/.default"
)

client = AzureOpenAI(
    azure_endpoint=endpoint,
    azure_ad_token_provider=token_provider,
    api_version="2025-01-01-preview",
)


# IMAGE_PATH = "YOUR_IMAGE_PATH"
# encoded_image = base64.b64encode(open(IMAGE_PATH, 'rb').read()).decode('ascii')
chat_prompt = [
    {
        "role": "system",
        "content": [
            {
                "type": "text",
                "text": "You are an AI assistant that helps people find information."
            }
        ]
    }
]

# Include speech result if speech is enabled
messages = chat_prompt

completion = client.chat.completions.create(
    model=deployment,
    messages=messages,
    max_tokens=16384,
    temperature=0.7,
    top_p=0.95,
    frequency_penalty=0,
    presence_penalty=0,
    stop=None,
    stream=False
)

print(completion.to_json())

endpoint="https://datascienceopenai-actualeastus2.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2025-01-01-preview"
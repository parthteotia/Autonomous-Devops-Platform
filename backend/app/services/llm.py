import boto3
import json
import os
from dotenv import load_dotenv

load_dotenv()

model_id = os.getenv("MODEL_ID")
region = os.getenv("AWS_REGION")

client = boto3.client("bedrock-runtime", region_name=region)


def ask_llm(prompt: str):

    # -------- Build request body based on provider --------
    if "anthropic" in model_id:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 500
        }

    elif "qwen" in model_id:
        body = {
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 500
        }

    elif "meta" in model_id:  # Llama models
        body = {
            "prompt": prompt,
            "max_gen_len": 512,
            "temperature": 0.7
        }

    elif "mistral" in model_id:
        body = {
            "prompt": prompt,
            "max_tokens": 512,
            "temperature": 0.7
        }

    elif "amazon.titan" in model_id:
        body = {
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": 512,
                "temperature": 0.7
            }
        }

    else:
        raise ValueError(f"Unsupported model: {model_id}")

    # -------- Call Bedrock --------
    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps(body)
    )

    result = json.loads(response["body"].read())

    # -------- Extract response safely --------
    if "content" in result:  # Anthropic / Qwen
        return result["content"][0]["text"]

    elif "choices" in result:  # OpenAI-like
        return result["choices"][0]["message"]["content"]

    elif "generation" in result:  # Mistral / Llama sometimes
        return result["generation"]

    elif "outputText" in result:  # Amazon Titan
        return result["outputText"]

    else:
        return str(result)
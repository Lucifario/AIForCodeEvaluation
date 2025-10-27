import os
import yaml
import logging
import time
from pathlib import Path
from typing import List, Dict, Optional
from openai import OpenAI, APIStatusError, RateLimitError, APITimeoutError
from dotenv import load_dotenv

class LLMClient:
    def __init__(self, config_path: str = 'config/config.yaml'):
        """
        Initializes the LLMClient.

        Args:
            config_path: Path to the main YAML configuration file.
        """
        try:
            with open(config_path, 'r') as f:
                self.config = yaml.safe_load(f)
        except FileNotFoundError:
            logging.error(f"Configuration file not found at {config_path}")
            raise
        except yaml.YAMLError as e:
            logging.error(f"Error parsing configuration file {config_path}: {e}")
            raise
        project_root = Path(__file__).parent.parent
        dotenv_path = project_root / '.env'
        if dotenv_path.exists():
            load_dotenv(dotenv_path=dotenv_path)
            logging.info("Loaded API keys from .env file.")
        else:
            logging.warning(f".env file not found at {dotenv_path}. API keys should be set as environment variables.")
        self.providers = self._load_provider_configs()
        self.models = self._load_model_configs()
        retry_config = self.config.get('multi_judge_config', {})
        self.max_retries = retry_config.get('max_retries', 3)
        self.initial_delay = retry_config.get('initial_delay', 2)


    def _load_provider_configs(self) -> Dict[str, Dict]:
        """Loads provider details (API key, base URL) from config and env vars."""
        providers_config = self.config.get('llm_providers', {})
        loaded_providers = {}
        for name, details in providers_config.items():
            api_key_env_var = details.get('api_key_env')
            api_key = os.getenv(api_key_env_var) if api_key_env_var else None
            base_url = details.get('base_url')
            if not api_key:
                logging.warning(f"API key environment variable '{api_key_env_var}' not set for provider '{name}'. Calls using this provider will fail.")
            if not base_url:
                logging.error(f"Base URL not configured for provider '{name}'.")
                continue
            loaded_providers[name] = {
                'api_key': api_key,
                'base_url': base_url
            }
        return loaded_providers

    def _load_model_configs(self) -> Dict[str, Dict]:
        """Creates a mapping from model_id to its full configuration including provider details."""
        models_config = self.config.get('llm_models', [])
        loaded_models = {}
        for model_info in models_config:
            model_id = model_info.get('id')
            provider_name = model_info.get('provider')
            model_name = model_info.get('model_name')
            role = model_info.get('role')
            if not all([model_id, provider_name, model_name]):
                logging.error(f"Incomplete configuration for a model (missing id, provider, or model_name): {model_info}. Skipping.")
                continue
            provider_details = self.providers.get(provider_name)
            if not provider_details:
                logging.error(f"Provider '{provider_name}' not found in llm_providers for model '{model_id}'. Skipping.")
                continue
            loaded_models[model_id] = {
                'provider': provider_name,
                'model_name': model_name,
                'role': role or 'unknown',
                'api_key': provider_details['api_key'],
                'base_url': provider_details['base_url']
            }
        logging.info(f"Loaded {len(loaded_models)} model configurations.")
        return loaded_models

    def query_llm(self, model_id: str, messages: List[Dict], use_json_mode: bool = False, temperature: float = 0.5, max_tokens: Optional[int] = None) -> Optional[str]:
        """
        Sends a request to the specified LLM and handles retries.

        Args:
            model_id: The unique ID from config.yaml (e.g., "llama3-70b-groq").
            messages: A list of message dictionaries (OpenAI format).
            use_json_mode: If True, request JSON output format.
            temperature: Sampling temperature for the model.
            max_tokens: Maximum number of tokens to generate.

        Returns:
            The content string of the LLM's response message, or None if an error occurs after retries.
        """
        model_config = self.models.get(model_id)
        if not model_config:
            logging.error(f"Model ID '{model_id}' not found in configuration.")
            return None
        if not model_config['api_key']:
             logging.error(f"API key for provider '{model_config['provider']}' (model '{model_id}') is not set. Cannot make API call.")
             return None
        try:
            client = OpenAI(
                api_key=model_config['api_key'],
                base_url=model_config['base_url']
            )
        except Exception as client_e:
             logging.error(f"Failed to initialize OpenAI client for {model_id}: {client_e}")
             return None
        request_params = {
            "model": model_config['model_name'],
            "messages": messages,
            "temperature": temperature,
        }
        if use_json_mode:
            request_params["response_format"] = {"type": "json_object"}
        if max_tokens:
            request_params["max_tokens"] = max_tokens

        current_delay = self.initial_delay
        for attempt in range(self.max_retries + 1):
            try:
                start_time = time.time()
                logging.info(f"Attempt {attempt + 1}/{self.max_retries + 1}: Calling model '{model_id}' ({model_config['model_name']}) via {model_config['provider']}...")
                if messages:
                     last_user_msg = next((msg['content'] for msg in reversed(messages) if msg['role'] == 'user'), None)
                     logging.debug(f"Prompt (last user msg start): {last_user_msg[:100] if last_user_msg else 'N/A'}...")
                completion = client.chat.completions.create(**request_params)
                response_time = time.time() - start_time
                if completion.choices and completion.choices[0].message:
                    response_content = completion.choices[0].message.content
                    logging.info(f"Model '{model_id}' responded successfully in {response_time:.2f}s.")
                    logging.debug(f"Response (start): {response_content[:100] if response_content else 'None'}...")
                    if response_content is None or response_content.strip() == "":
                        logging.warning(f"Model '{model_id}' returned an empty response content.")
                        return ""
                    return response_content
                else:
                    logging.error(f"Model '{model_id}' returned unexpected response structure: {completion}. Retrying in {current_delay}s...")
                    response_content = None
            except RateLimitError as e:
                logging.warning(f"Rate limit error for model '{model_id}' (Attempt {attempt + 1}): {e}. Retrying in {current_delay}s...")
            except APITimeoutError as e:
                logging.warning(f"API timeout error for model '{model_id}' (Attempt {attempt + 1}): {e}. Retrying in {current_delay}s...")
            except APIStatusError as e:
                error_details = "No additional details provided."
                try: error_details = e.response.json()
                except:
                    try: error_details = e.response.text
                    except: pass
                logging.error(f"API status error for model '{model_id}' (Attempt {attempt + 1}): {e.status_code} - {e.message}. Details: {error_details}. Retrying in {current_delay}s...")
            except Exception as e:
                logging.error(f"Unexpected error during API call for model '{model_id}' (Attempt {attempt + 1}): {e}", exc_info=False)
            if attempt < self.max_retries:
                logging.info(f"Waiting {current_delay}s before retry...")
                time.sleep(current_delay)
                current_delay = min(current_delay * 2, 60)
            else:
                 logging.error(f"Failed to get valid response from model '{model_id}' after {self.max_retries + 1} attempts.")
                 return None

if __name__ == '__main__':
    log_level = logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)-8s - %(message)s')
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    config_file_path = project_root / 'config/config.yaml'
    dotenv_path = project_root / '.env'
    if not config_file_path.exists():
         print(f"CRITICAL ERROR: config.yaml not found at {config_file_path}")
         exit(1)
    if not dotenv_path.exists():
         print(f"CRITICAL ERROR: .env file not found at {dotenv_path}")
         exit(1)
    try:
        llm_client = LLMClient(config_path=str(config_file_path))
        if not llm_client.models:
            print("CRITICAL ERROR: No models loaded. Check config.")
            exit(1)
        print("\n--- Testing Groq Llama 3 8B ---")
        if "llama3-8b-groq" in llm_client.models:
            messages_groq = [{"role": "system", "content": "You are helpful."}, {"role": "user", "content": "Explain recursion simply."}]
            response_groq = llm_client.query_llm("llama3-8b-groq", messages_groq)
            print("Response:", response_groq if response_groq is not None else "Failed")
        else: print("Skipping Groq 8B test: ID not found in config.")
        mistral_id_to_test = "Mistral-Small-3.2-24B-Instruct-2506"
        print(f"\n--- Testing OpenRouter Mistral ({mistral_id_to_test}) ---")
        if mistral_id_to_test in llm_client.models:
            messages_mistral = [{"role": "system", "content": "You are helpful."}, {"role": "user", "content": "Capital of France?"}]
            response_mistral = llm_client.query_llm(mistral_id_to_test, messages_mistral)
            print("Response:", response_mistral if response_mistral is not None else "Failed")
        else: print(f"Skipping Mistral test: ID '{mistral_id_to_test}' not found in config.")
        gemma_id_to_test = "gemma-27b-or"
        print(f"\n--- Testing OpenRouter Gemma ({gemma_id_to_test}) ---")
        if gemma_id_to_test in llm_client.models:
            messages_gemma = [{"role": "system", "content": "You are helpful."}, {"role": "user", "content": "What is 2 + 2?"}]
            response_gemma = llm_client.query_llm(gemma_id_to_test, messages_gemma)
            print("Response:", response_gemma if response_gemma is not None else "Failed")
        else: print(f"Skipping Gemma test: ID '{gemma_id_to_test}' not found in config.")
    except Exception as main_e:
        print(f"\nAn error occurred during testing: {main_e}")
        logging.exception("Testing failed")
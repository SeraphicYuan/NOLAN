"""LLM clients for NOLAN (Gemini + OpenRouter text)."""

import google.generativeai as genai
import httpx
from typing import Optional


class OpenRouterLLM:
    """OpenAI-compatible text LLM client (OpenRouter), drop-in for GeminiClient.

    Exposes the same async ``generate(prompt, system_prompt=None)`` interface that
    SceneDesigner/ScriptConverter expect, so any OpenRouter text model (qwen,
    tencent/hy3-preview, etc.) can replace Gemini for script→scenes design.
    """

    def __init__(self, api_key: str, model: str,
                 base_url: str = "https://openrouter.ai/api/v1",
                 reasoning_enabled: bool = False, timeout: float = 180.0):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.reasoning_enabled = reasoning_enabled
        self.timeout = timeout

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {"model": self.model, "messages": messages}
        if not self.reasoning_enabled:
            payload["reasoning"] = {"enabled": False}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/nolan",
            "X-Title": "NOLAN",
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=10.0)) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"OpenRouter returned no choices: {str(data)[:200]}")
        return (choices[0]["message"].get("content") or "").strip()


def create_text_llm(config, provider: Optional[str] = None,
                    model: Optional[str] = None, reasoning: Optional[bool] = None):
    """Build the text LLM for authoring tasks (script, scenes, clustering, …).

    Resolves provider/model from `config.llm` unless overridden. Defaults to
    qwen/qwen3.7-plus via OpenRouter; pass provider="gemini" to use Gemini.

    Args:
        config: NolanConfig.
        provider: "openrouter" | "gemini" (overrides config.llm.provider).
        model: model id (overrides config.llm.model / config.gemini.model).
        reasoning: enable reasoning for OpenRouter models (default config.llm).
    """
    provider = (provider or config.llm.provider).lower()
    if provider == "gemini":
        return GeminiClient(api_key=config.gemini.api_key,
                            model=model or config.gemini.model)
    # OpenRouter (default) — any text model. Key/base_url reused from vision config.
    re_enabled = config.llm.reasoning_enabled if reasoning is None else reasoning
    return OpenRouterLLM(
        api_key=config.vision.openrouter_api_key,
        model=model or config.llm.model,
        base_url=config.vision.base_url,
        reasoning_enabled=re_enabled,
    )


class GeminiClient:
    """Client for interacting with Gemini API."""

    def __init__(self, api_key: str, model: str = "gemini-3-flash-preview"):
        """Initialize the Gemini client.

        Args:
            api_key: Gemini API key.
            model: Model name to use.
        """
        self.api_key = api_key
        self.model = model
        genai.configure(api_key=api_key)
        self._client = genai.GenerativeModel(model)

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate text from a prompt.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system instructions.

        Returns:
            Generated text response.
        """
        return await self._call_api(prompt, system_prompt)

    async def _call_api(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Make the actual API call.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system instructions.

        Returns:
            Generated text response.
        """
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        response = await self._client.generate_content_async(full_prompt)
        return response.text

    async def generate_with_image(self, prompt: str, image_path: str) -> str:
        """Generate text from a prompt with an image.

        Args:
            prompt: The user prompt.
            image_path: Path to the image file.

        Returns:
            Generated text response.
        """
        import PIL.Image
        image = PIL.Image.open(image_path)
        response = await self._client.generate_content_async([prompt, image])
        return response.text

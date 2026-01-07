"""Gemini LLM client for NOLAN."""

import google.generativeai as genai
from typing import Optional


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

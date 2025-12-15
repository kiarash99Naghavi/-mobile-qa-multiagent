"""
Gemini LLM client for multimodal mobile QA.
Uses the official google-genai SDK.
"""
import os
import json
import base64
from pathlib import Path
from typing import Optional, Dict, Any, List

from google import genai


class GeminiClient:
    """Client for Google Gemini API using google-genai SDK."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-1.5-flash"):
        """
        Initialize Gemini client.

        Args:
            api_key: Gemini API key. If None, reads from GEMINI_API_KEY env var.
            model: Model to use (default: gemini-1.5-flash)
        """
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found. Set environment variable or pass api_key parameter.")

        self.model = model
        self.client = genai.Client(api_key=self.api_key)

    def _load_image(self, image_path: str) -> Dict[str, Any]:
        """
        Load image for Gemini API.

        Args:
            image_path: Path to image file

        Returns:
            Image part dictionary for API
        """
        with open(image_path, 'rb') as f:
            image_data = f.read()

        # Determine MIME type from extension
        ext = Path(image_path).suffix.lower()
        mime_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }
        mime_type = mime_types.get(ext, 'image/png')

        return {
            'inline_data': {
                'mime_type': mime_type,
                'data': base64.b64encode(image_data).decode('utf-8')
            }
        }

    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> str:
        """
        Generate text response from Gemini.

        Args:
            prompt: User prompt
            system_instruction: Optional system instruction
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text response
        """
        config = {
            'temperature': temperature,
            'max_output_tokens': max_tokens,
        }

        contents = [prompt]

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config
        )

        if response.text is None:
            return ""  # Return empty string instead of None
        return response.text

    def generate_with_image(
        self,
        prompt: str,
        image_path: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> str:
        """
        Generate text response with image input.

        Args:
            prompt: User prompt
            image_path: Path to image file
            system_instruction: Optional system instruction
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text response
        """
        config = {
            'temperature': temperature,
            'max_output_tokens': max_tokens,
        }

        # Create multimodal content
        image_part = self._load_image(image_path)
        contents = [
            image_part,
            prompt
        ]

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config
        )

        if response.text is None:
            return ""  # Return empty string instead of None
        return response.text

    def generate_json(
        self,
        prompt: str,
        image_path: Optional[str] = None,
        system_instruction: Optional[str] = None,
        temperature: float = 0.5,
        max_tokens: int = 2048
    ) -> Dict[str, Any]:
        """
        Generate structured JSON response.

        Args:
            prompt: User prompt (should request JSON format)
            image_path: Optional path to image file
            system_instruction: Optional system instruction
            temperature: Sampling temperature (lower for more deterministic)
            max_tokens: Maximum tokens to generate

        Returns:
            Parsed JSON response as dictionary
        """
        # Add JSON formatting instruction to prompt
        json_prompt = f"{prompt}\n\nRespond with valid JSON only, no other text."

        if image_path:
            response_text = self.generate_with_image(
                json_prompt, image_path, system_instruction, temperature, max_tokens
            )
        else:
            response_text = self.generate_text(
                json_prompt, system_instruction, temperature, max_tokens
            )

        # Handle None or empty response
        if response_text is None or not response_text:
            raise ValueError("Gemini API returned empty response")

        # Extract JSON from response (handle markdown code blocks)
        response_text = response_text.strip()

        # Remove markdown code blocks if present
        if response_text.startswith('```'):
            lines = response_text.split('\n')
            # Remove first and last lines (```)
            if lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            response_text = '\n'.join(lines)

        # Parse JSON
        try:
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            # Try to find JSON object in text
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            raise ValueError(f"Failed to parse JSON response: {e}\nResponse: {response_text}")

    def generate_multimodal(
        self,
        text_parts: List[str],
        image_paths: List[str],
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> str:
        """
        Generate response with multiple text and image parts.

        Args:
            text_parts: List of text prompts
            image_paths: List of image file paths
            system_instruction: Optional system instruction
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text response
        """
        config = {
            'temperature': temperature,
            'max_output_tokens': max_tokens,
        }

        # Build interleaved content
        contents = []
        for text, img_path in zip(text_parts, image_paths):
            if img_path:
                contents.append(self._load_image(img_path))
            if text:
                contents.append(text)

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config
        )

        return response.text

# NOLAN Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a CLI tool that transforms structured essays into video production packages with scripts, scene plans, and organized assets.

**Architecture:** Modular Python CLI with separate components for script conversion, scene design, video indexing, ComfyUI integration, and a local viewer. Each stage outputs files for inspection/editing before continuing.

**Tech Stack:** Python 3.x, Gemini API, SQLite, FastAPI, Click (CLI), python-dotenv, PyYAML, opencv-python

---

## Task 1: Project Setup

**Files:**
- Create: `src/nolan/__init__.py`
- Create: `src/nolan/cli.py`
- Create: `pyproject.toml`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Step 1: Create project structure**

```
D:\ClaudeProjects\NOLAN\
├── src/
│   └── nolan/
│       └── __init__.py
├── tests/
│   ├── __init__.py
│   └── conftest.py
├── pyproject.toml
└── .env
```

**Step 2: Write pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "nolan"
version = "0.1.0"
description = "Video essay pipeline - transform essays into production-ready video packages"
requires-python = ">=3.10"
dependencies = [
    "click>=8.0",
    "python-dotenv>=1.0",
    "pyyaml>=6.0",
    "google-generativeai>=0.4",
    "opencv-python>=4.8",
    "fastapi>=0.100",
    "uvicorn>=0.20",
    "httpx>=0.24",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
]

[project.scripts]
nolan = "nolan.cli:main"

[tool.setuptools.packages.find]
where = ["src"]
```

**Step 3: Write src/nolan/__init__.py**

```python
"""NOLAN - Video Essay Pipeline."""

__version__ = "0.1.0"
```

**Step 4: Write tests/conftest.py**

```python
"""Pytest configuration and fixtures."""

import os
import pytest
from pathlib import Path

@pytest.fixture
def sample_essay_path():
    """Path to the sample Venezuela essay."""
    return Path(r"D:\ClaudeProjects\NOLAN\draft-20260104-110039.md")

@pytest.fixture
def sample_essay(sample_essay_path):
    """Load sample essay content."""
    return sample_essay_path.read_text(encoding="utf-8")

@pytest.fixture
def temp_output_dir(tmp_path):
    """Create a temporary output directory for tests."""
    output = tmp_path / "output"
    output.mkdir()
    return output
```

**Step 5: Write tests/__init__.py**

```python
"""Test package for NOLAN."""
```

**Step 6: Install package in dev mode**

Run: `D:\env\nolan\Scripts\pip.exe install -e ".[dev]"`

Expected: Successfully installed nolan and dependencies

**Step 7: Verify installation**

Run: `D:\env\nolan\python.exe -c "import nolan; print(nolan.__version__)"`

Expected: `0.1.0`

**Step 8: Commit**

```bash
git init
git add .
git commit -m "chore: initial project setup with dependencies"
```

---

## Task 2: Configuration System

**Files:**
- Create: `src/nolan/config.py`
- Create: `tests/test_config.py`

**Step 1: Write the failing test**

```python
# tests/test_config.py
"""Tests for configuration loading."""

import pytest
from pathlib import Path

from nolan.config import load_config, NolanConfig


def test_load_config_from_env(monkeypatch, tmp_path):
    """Config loads GEMINI_API_KEY from environment."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

    config = load_config()

    assert config.gemini.api_key == "test-api-key"


def test_config_has_defaults():
    """Config provides sensible defaults."""
    config = load_config()

    assert config.gemini.model == "gemini-3-flash-preview"
    assert config.defaults.words_per_minute == 150
    assert config.comfyui.host == "127.0.0.1"
    assert config.comfyui.port == 8188
    assert config.indexing.frame_interval == 5


def test_load_config_from_yaml(tmp_path, monkeypatch):
    """Config loads overrides from YAML file."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
defaults:
  words_per_minute: 120
""")

    config = load_config(config_path=config_file)

    assert config.defaults.words_per_minute == 120
```

**Step 2: Run test to verify it fails**

Run: `D:\env\nolan\python.exe -m pytest tests/test_config.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'nolan.config'"

**Step 3: Write minimal implementation**

```python
# src/nolan/config.py
"""Configuration management for NOLAN."""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import yaml
from dotenv import load_dotenv


@dataclass
class GeminiConfig:
    """Gemini API configuration."""
    api_key: str = ""
    model: str = "gemini-3-flash-preview"


@dataclass
class ComfyUIConfig:
    """ComfyUI connection configuration."""
    host: str = "127.0.0.1"
    port: int = 8188
    workflow: str = "default"
    width: int = 1920
    height: int = 1080
    steps: int = 20


@dataclass
class IndexingConfig:
    """Video indexing configuration."""
    frame_interval: int = 5
    database: str = "~/.nolan/library.db"


@dataclass
class DefaultsConfig:
    """Default processing settings."""
    words_per_minute: int = 150
    output_dir: str = "./output"


@dataclass
class NolanConfig:
    """Main configuration container."""
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    comfyui: ComfyUIConfig = field(default_factory=ComfyUIConfig)
    indexing: IndexingConfig = field(default_factory=IndexingConfig)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)


def load_config(config_path: Optional[Path] = None) -> NolanConfig:
    """Load configuration from environment and optional YAML file.

    Args:
        config_path: Optional path to YAML config file.

    Returns:
        Populated NolanConfig instance.
    """
    # Load .env file from current directory
    load_dotenv()

    config = NolanConfig()

    # Load API key from environment
    config.gemini.api_key = os.getenv("GEMINI_API_KEY", "")

    # Load YAML overrides if provided
    if config_path and config_path.exists():
        with open(config_path) as f:
            overrides = yaml.safe_load(f) or {}

        if "gemini" in overrides:
            for key, value in overrides["gemini"].items():
                if hasattr(config.gemini, key):
                    setattr(config.gemini, key, value)

        if "comfyui" in overrides:
            for key, value in overrides["comfyui"].items():
                if hasattr(config.comfyui, key):
                    setattr(config.comfyui, key, value)

        if "indexing" in overrides:
            for key, value in overrides["indexing"].items():
                if hasattr(config.indexing, key):
                    setattr(config.indexing, key, value)

        if "defaults" in overrides:
            for key, value in overrides["defaults"].items():
                if hasattr(config.defaults, key):
                    setattr(config.defaults, key, value)

    return config
```

**Step 4: Run test to verify it passes**

Run: `D:\env\nolan\python.exe -m pytest tests/test_config.py -v`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add src/nolan/config.py tests/test_config.py
git commit -m "feat: add configuration system with env and YAML support"
```

---

## Task 3: Gemini Client

**Files:**
- Create: `src/nolan/llm.py`
- Create: `tests/test_llm.py`

**Step 1: Write the failing test**

```python
# tests/test_llm.py
"""Tests for LLM client."""

import pytest
from unittest.mock import Mock, patch

from nolan.llm import GeminiClient


def test_gemini_client_initialization():
    """Client initializes with API key."""
    client = GeminiClient(api_key="test-key", model="gemini-3-flash-preview")

    assert client.api_key == "test-key"
    assert client.model == "gemini-3-flash-preview"


@pytest.mark.asyncio
async def test_generate_text_returns_response():
    """Client returns generated text from API."""
    client = GeminiClient(api_key="test-key", model="gemini-3-flash-preview")

    with patch.object(client, '_call_api') as mock_call:
        mock_call.return_value = "Generated response"

        result = await client.generate("Test prompt")

        assert result == "Generated response"
        mock_call.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `D:\env\nolan\python.exe -m pytest tests/test_llm.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'nolan.llm'"

**Step 3: Write minimal implementation**

```python
# src/nolan/llm.py
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
```

**Step 4: Run test to verify it passes**

Run: `D:\env\nolan\python.exe -m pytest tests/test_llm.py -v`

Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add src/nolan/llm.py tests/test_llm.py
git commit -m "feat: add Gemini LLM client"
```

---

## Task 4: Essay Parser

**Files:**
- Create: `src/nolan/parser.py`
- Create: `tests/test_parser.py`

**Step 1: Write the failing test**

```python
# tests/test_parser.py
"""Tests for essay parsing."""

import pytest
from nolan.parser import parse_essay, Section


def test_parse_essay_extracts_sections():
    """Parser extracts markdown sections."""
    essay = """## Hook

This is the hook content.
It has multiple lines.

## Context

This is context content.
"""

    sections = parse_essay(essay)

    assert len(sections) == 2
    assert sections[0].title == "Hook"
    assert "hook content" in sections[0].content
    assert sections[1].title == "Context"


def test_parse_essay_calculates_word_count():
    """Parser calculates word count per section."""
    essay = """## Section One

One two three four five.

## Section Two

Six seven eight.
"""

    sections = parse_essay(essay)

    assert sections[0].word_count == 5
    assert sections[1].word_count == 3


def test_parse_real_essay(sample_essay):
    """Parser handles the Venezuela sample essay."""
    sections = parse_essay(sample_essay)

    assert len(sections) == 7
    assert sections[0].title == "Hook"
    assert sections[1].title == "Context"
    assert sections[2].title == "Thesis"
    assert sections[3].title == "Evidence 1"
    assert sections[6].title == "Conclusion"
```

**Step 2: Run test to verify it fails**

Run: `D:\env\nolan\python.exe -m pytest tests/test_parser.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'nolan.parser'"

**Step 3: Write minimal implementation**

```python
# src/nolan/parser.py
"""Essay parsing for NOLAN."""

import re
from dataclasses import dataclass
from typing import List


@dataclass
class Section:
    """A section of the essay."""
    title: str
    content: str
    word_count: int

    @property
    def estimated_duration_seconds(self) -> float:
        """Estimate duration at 150 words per minute."""
        return (self.word_count / 150) * 60


def parse_essay(text: str) -> List[Section]:
    """Parse a markdown essay into sections.

    Args:
        text: The essay text in markdown format.

    Returns:
        List of Section objects.
    """
    # Split on ## headers (level 2)
    pattern = r'^##\s+(.+?)$'

    sections = []
    current_title = None
    current_content = []

    for line in text.split('\n'):
        header_match = re.match(pattern, line)

        if header_match:
            # Save previous section if exists
            if current_title is not None:
                content = '\n'.join(current_content).strip()
                word_count = len(content.split())
                sections.append(Section(
                    title=current_title,
                    content=content,
                    word_count=word_count
                ))

            # Start new section
            current_title = header_match.group(1).strip()
            current_content = []
        else:
            current_content.append(line)

    # Don't forget the last section
    if current_title is not None:
        content = '\n'.join(current_content).strip()
        word_count = len(content.split())
        sections.append(Section(
            title=current_title,
            content=content,
            word_count=word_count
        ))

    return sections
```

**Step 4: Run test to verify it passes**

Run: `D:\env\nolan\python.exe -m pytest tests/test_parser.py -v`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add src/nolan/parser.py tests/test_parser.py
git commit -m "feat: add essay markdown parser"
```

---

## Task 5: Script Converter

**Files:**
- Create: `src/nolan/script.py`
- Create: `tests/test_script.py`
- Create: `src/nolan/prompts/script_conversion.txt`

**Step 1: Write the failing test**

```python
# tests/test_script.py
"""Tests for script conversion."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from nolan.script import ScriptConverter, ScriptSection
from nolan.parser import Section


@pytest.fixture
def mock_llm():
    """Create a mock LLM client."""
    client = Mock()
    client.generate = AsyncMock(return_value="""Venezuela. A land of stunning beauty.

Now, let's look at what makes this nation so complex. Every day, millions struggle just to get by.""")
    return client


def test_script_section_has_timestamp():
    """Script section includes calculated timestamp."""
    section = ScriptSection(
        title="Hook",
        narration="This is the narration text.",
        start_time=0.0,
        end_time=45.0,
        word_count=5
    )

    assert section.timestamp == "0:00 - 0:45"


@pytest.mark.asyncio
async def test_convert_section_calls_llm(mock_llm):
    """Converter uses LLM to transform section."""
    converter = ScriptConverter(llm_client=mock_llm)
    section = Section(title="Hook", content="Original content here.", word_count=3)

    result = await converter.convert_section(section, start_time=0.0)

    assert mock_llm.generate.called
    assert result.title == "Hook"
    assert len(result.narration) > 0


@pytest.mark.asyncio
async def test_convert_essay_produces_full_script(mock_llm):
    """Converter produces complete script with all sections."""
    converter = ScriptConverter(llm_client=mock_llm)
    sections = [
        Section(title="Hook", content="Hook content.", word_count=150),
        Section(title="Context", content="Context content.", word_count=300),
    ]

    script = await converter.convert_essay(sections)

    assert len(script.sections) == 2
    assert script.sections[0].start_time == 0.0
    assert script.sections[1].start_time > 0  # Continues from previous
    assert script.total_duration > 0
```

**Step 2: Run test to verify it fails**

Run: `D:\env\nolan\python.exe -m pytest tests/test_script.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'nolan.script'"

**Step 3: Create prompt template**

```
# src/nolan/prompts/script_conversion.txt

You are converting a written essay section into a YouTube video narration script.

SECTION TITLE: {title}

ORIGINAL CONTENT:
{content}

INSTRUCTIONS:
1. Adapt the text for spoken word - it should sound natural when read aloud
2. Shorten complex sentences - break them into digestible pieces
3. Add verbal transitions where appropriate ("Now, let's look at...", "Here's the key insight...")
4. Remove parentheticals and dense citations that don't work in speech
5. Maintain the original meaning and key points
6. Keep the same approximate length (don't significantly expand or shorten)

OUTPUT:
Return ONLY the converted narration text. Do not include the section title or any other formatting.
```

**Step 4: Write the implementation**

```python
# src/nolan/script.py
"""Script conversion for NOLAN."""

from dataclasses import dataclass, field
from typing import List
from pathlib import Path

from nolan.parser import Section


PROMPT_TEMPLATE = """You are converting a written essay section into a YouTube video narration script.

SECTION TITLE: {title}

ORIGINAL CONTENT:
{content}

INSTRUCTIONS:
1. Adapt the text for spoken word - it should sound natural when read aloud
2. Shorten complex sentences - break them into digestible pieces
3. Add verbal transitions where appropriate ("Now, let's look at...", "Here's the key insight...")
4. Remove parentheticals and dense citations that don't work in speech
5. Maintain the original meaning and key points
6. Keep the same approximate length (don't significantly expand or shorten)

OUTPUT:
Return ONLY the converted narration text. Do not include the section title or any other formatting."""


def format_timestamp(seconds: float) -> str:
    """Format seconds as M:SS or H:MM:SS."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes >= 60:
        hours = minutes // 60
        minutes = minutes % 60
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


@dataclass
class ScriptSection:
    """A section of the converted script."""
    title: str
    narration: str
    start_time: float
    end_time: float
    word_count: int

    @property
    def timestamp(self) -> str:
        """Format as 'M:SS - M:SS'."""
        return f"{format_timestamp(self.start_time)} - {format_timestamp(self.end_time)}"

    @property
    def duration(self) -> float:
        """Duration in seconds."""
        return self.end_time - self.start_time


@dataclass
class Script:
    """Complete converted script."""
    sections: List[ScriptSection] = field(default_factory=list)

    @property
    def total_duration(self) -> float:
        """Total duration in seconds."""
        if not self.sections:
            return 0.0
        return self.sections[-1].end_time

    def to_markdown(self) -> str:
        """Export script as markdown."""
        lines = ["# Video Script\n"]
        lines.append(f"**Total Duration:** {format_timestamp(self.total_duration)}\n")
        lines.append("---\n")

        for section in self.sections:
            lines.append(f"## {section.title} [{section.timestamp}]\n")
            lines.append(section.narration)
            lines.append("\n")

        return "\n".join(lines)


class ScriptConverter:
    """Converts essay sections to video script narration."""

    def __init__(self, llm_client, words_per_minute: int = 150):
        """Initialize the converter.

        Args:
            llm_client: The LLM client to use for conversion.
            words_per_minute: Speaking rate for duration estimation.
        """
        self.llm = llm_client
        self.words_per_minute = words_per_minute

    async def convert_section(self, section: Section, start_time: float = 0.0) -> ScriptSection:
        """Convert a single section to script narration.

        Args:
            section: The essay section to convert.
            start_time: Start time in seconds.

        Returns:
            Converted ScriptSection.
        """
        prompt = PROMPT_TEMPLATE.format(
            title=section.title,
            content=section.content
        )

        narration = await self.llm.generate(prompt)
        narration = narration.strip()

        # Calculate timing based on output word count
        word_count = len(narration.split())
        duration = (word_count / self.words_per_minute) * 60

        return ScriptSection(
            title=section.title,
            narration=narration,
            start_time=start_time,
            end_time=start_time + duration,
            word_count=word_count
        )

    async def convert_essay(self, sections: List[Section]) -> Script:
        """Convert all sections to a complete script.

        Args:
            sections: List of essay sections.

        Returns:
            Complete Script object.
        """
        script = Script()
        current_time = 0.0

        for section in sections:
            script_section = await self.convert_section(section, start_time=current_time)
            script.sections.append(script_section)
            current_time = script_section.end_time

        return script
```

**Step 5: Run test to verify it passes**

Run: `D:\env\nolan\python.exe -m pytest tests/test_script.py -v`

Expected: PASS (3 tests)

**Step 6: Commit**

```bash
git add src/nolan/script.py tests/test_script.py
git commit -m "feat: add essay to script converter with LLM"
```

---

## Task 6: Scene Designer

**Files:**
- Create: `src/nolan/scenes.py`
- Create: `tests/test_scenes.py`

**Step 1: Write the failing test**

```python
# tests/test_scenes.py
"""Tests for scene design."""

import pytest
import json
from unittest.mock import Mock, AsyncMock

from nolan.scenes import SceneDesigner, Scene, ScenePlan
from nolan.script import ScriptSection


@pytest.fixture
def mock_llm():
    """Create a mock LLM client that returns valid JSON."""
    client = Mock()
    client.generate = AsyncMock(return_value=json.dumps([
        {
            "id": "scene_001",
            "start": "0:00",
            "duration": "10s",
            "narration_excerpt": "Venezuela. A land of stunning beauty.",
            "visual_type": "b-roll",
            "visual_description": "Aerial shot of Venezuelan landscape with mountains and waterfalls",
            "asset_suggestions": {
                "search_query": "venezuela aerial landscape mountains",
                "comfyui_prompt": "aerial photography, venezuelan andes mountains, lush green valleys, dramatic clouds, 4k cinematic",
                "library_match": True
            }
        },
        {
            "id": "scene_002",
            "start": "0:10",
            "duration": "15s",
            "narration_excerpt": "cascading waterfalls, vibrant rainforests",
            "visual_type": "b-roll",
            "visual_description": "Angel Falls waterfall in Venezuela",
            "asset_suggestions": {
                "search_query": "angel falls venezuela waterfall",
                "comfyui_prompt": "angel falls, tallest waterfall, mist, tropical rainforest, dramatic lighting",
                "library_match": True
            }
        }
    ]))
    return client


def test_scene_has_required_fields():
    """Scene object contains all required fields."""
    scene = Scene(
        id="scene_001",
        start="0:00",
        duration="10s",
        narration_excerpt="Test narration",
        visual_type="b-roll",
        visual_description="Test description",
        search_query="test query",
        comfyui_prompt="test prompt",
        library_match=True
    )

    assert scene.id == "scene_001"
    assert scene.visual_type == "b-roll"


@pytest.mark.asyncio
async def test_design_scenes_for_section(mock_llm):
    """Designer generates scenes for a script section."""
    designer = SceneDesigner(llm_client=mock_llm)
    section = ScriptSection(
        title="Hook",
        narration="Venezuela. A land of stunning beauty - cascading waterfalls.",
        start_time=0.0,
        end_time=45.0,
        word_count=8
    )

    scenes = await designer.design_section(section)

    assert len(scenes) == 2
    assert scenes[0].id == "scene_001"
    assert "venezuela" in scenes[0].visual_description.lower()


@pytest.mark.asyncio
async def test_scene_plan_exports_to_json(mock_llm):
    """Scene plan can be exported to JSON."""
    designer = SceneDesigner(llm_client=mock_llm)
    section = ScriptSection(
        title="Hook",
        narration="Test narration.",
        start_time=0.0,
        end_time=30.0,
        word_count=2
    )

    scenes = await designer.design_section(section)
    plan = ScenePlan(sections={"Hook": scenes})

    json_output = plan.to_json()
    parsed = json.loads(json_output)

    assert "Hook" in parsed["sections"]
    assert len(parsed["sections"]["Hook"]) == 2
```

**Step 2: Run test to verify it fails**

Run: `D:\env\nolan\python.exe -m pytest tests/test_scenes.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'nolan.scenes'"

**Step 3: Write the implementation**

```python
# src/nolan/scenes.py
"""Scene design for NOLAN."""

import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional

from nolan.script import ScriptSection


SCENE_DESIGN_PROMPT = """You are designing visual scenes for a YouTube video essay.

SECTION: {title}
TIMESTAMP: {timestamp}
NARRATION:
{narration}

Design a sequence of visual scenes to accompany this narration. For each scene, specify:
- When it starts and how long it lasts
- What type of visual (b-roll, graphic, text-overlay, generated-image)
- What should appear on screen
- Search terms for finding stock footage
- A prompt for AI image generation (if applicable)

Return a JSON array of scenes with this structure:
[
  {{
    "id": "scene_XXX",
    "start": "M:SS",
    "duration": "Xs",
    "narration_excerpt": "the specific words being spoken",
    "visual_type": "b-roll|graphic|text-overlay|generated-image",
    "visual_description": "detailed description of what appears on screen",
    "asset_suggestions": {{
      "search_query": "keywords for stock footage search",
      "comfyui_prompt": "detailed prompt for AI image generation",
      "library_match": true
    }}
  }}
]

IMPORTANT: Return ONLY the JSON array, no other text."""


@dataclass
class Scene:
    """A single visual scene."""
    id: str
    start: str
    duration: str
    narration_excerpt: str
    visual_type: str  # b-roll, graphic, text-overlay, generated-image
    visual_description: str
    search_query: str
    comfyui_prompt: str
    library_match: bool
    skip_generation: bool = False
    matched_asset: Optional[str] = None
    generated_asset: Optional[str] = None


@dataclass
class ScenePlan:
    """Complete scene plan for a video."""
    sections: Dict[str, List[Scene]] = field(default_factory=dict)

    def to_json(self, indent: int = 2) -> str:
        """Export to JSON string."""
        data = {
            "sections": {
                title: [asdict(scene) for scene in scenes]
                for title, scenes in self.sections.items()
            }
        }
        return json.dumps(data, indent=indent)

    def save(self, path: str) -> None:
        """Save to JSON file."""
        with open(path, 'w') as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, path: str) -> "ScenePlan":
        """Load from JSON file."""
        with open(path, 'r') as f:
            data = json.load(f)

        plan = cls()
        for title, scenes_data in data["sections"].items():
            plan.sections[title] = [
                Scene(**scene) for scene in scenes_data
            ]
        return plan

    @property
    def all_scenes(self) -> List[Scene]:
        """Get all scenes flattened."""
        scenes = []
        for section_scenes in self.sections.values():
            scenes.extend(section_scenes)
        return scenes


class SceneDesigner:
    """Designs visual scenes for script sections."""

    def __init__(self, llm_client):
        """Initialize the designer.

        Args:
            llm_client: The LLM client for scene generation.
        """
        self.llm = llm_client

    async def design_section(self, section: ScriptSection) -> List[Scene]:
        """Design scenes for a single script section.

        Args:
            section: The script section to design for.

        Returns:
            List of Scene objects.
        """
        prompt = SCENE_DESIGN_PROMPT.format(
            title=section.title,
            timestamp=section.timestamp,
            narration=section.narration
        )

        response = await self.llm.generate(prompt)

        # Parse JSON response
        try:
            scenes_data = json.loads(response.strip())
        except json.JSONDecodeError:
            # Try to extract JSON from response
            import re
            match = re.search(r'\[.*\]', response, re.DOTALL)
            if match:
                scenes_data = json.loads(match.group())
            else:
                raise ValueError(f"Could not parse scene JSON from response: {response[:200]}")

        scenes = []
        for scene_data in scenes_data:
            scene = Scene(
                id=scene_data["id"],
                start=scene_data["start"],
                duration=scene_data["duration"],
                narration_excerpt=scene_data["narration_excerpt"],
                visual_type=scene_data["visual_type"],
                visual_description=scene_data["visual_description"],
                search_query=scene_data["asset_suggestions"]["search_query"],
                comfyui_prompt=scene_data["asset_suggestions"]["comfyui_prompt"],
                library_match=scene_data["asset_suggestions"].get("library_match", True)
            )
            scenes.append(scene)

        return scenes

    async def design_full_plan(self, sections: List[ScriptSection]) -> ScenePlan:
        """Design scenes for all script sections.

        Args:
            sections: List of script sections.

        Returns:
            Complete ScenePlan.
        """
        plan = ScenePlan()

        for section in sections:
            scenes = await self.design_section(section)
            plan.sections[section.title] = scenes

        return plan
```

**Step 4: Run test to verify it passes**

Run: `D:\env\nolan\python.exe -m pytest tests/test_scenes.py -v`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add src/nolan/scenes.py tests/test_scenes.py
git commit -m "feat: add scene designer with LLM-powered visual planning"
```

---

## Task 7: Video Indexer

**Files:**
- Create: `src/nolan/indexer.py`
- Create: `tests/test_indexer.py`

**Step 1: Write the failing test**

```python
# tests/test_indexer.py
"""Tests for video indexing."""

import pytest
import sqlite3
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

from nolan.indexer import VideoIndexer, VideoIndex, VideoSegment


@pytest.fixture
def mock_llm():
    """Mock LLM for frame analysis."""
    client = Mock()
    client.generate_with_image = AsyncMock(return_value="City skyline at sunset with tall buildings and orange sky")
    return client


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database path."""
    return tmp_path / "test_library.db"


def test_video_index_creates_database(temp_db):
    """Index creates SQLite database on init."""
    index = VideoIndex(temp_db)

    assert temp_db.exists()


def test_video_index_stores_and_retrieves_segments(temp_db):
    """Index can store and retrieve video segments."""
    index = VideoIndex(temp_db)

    index.add_video(
        path="/videos/test.mp4",
        duration=120.0,
        checksum="abc123"
    )

    index.add_segment(
        video_path="/videos/test.mp4",
        timestamp=5.0,
        description="A person walking in a park"
    )

    segments = index.get_segments("/videos/test.mp4")

    assert len(segments) == 1
    assert segments[0].description == "A person walking in a park"


def test_video_index_search_returns_matches(temp_db):
    """Index search returns matching segments."""
    index = VideoIndex(temp_db)

    index.add_video("/videos/city.mp4", 60.0, "def456")
    index.add_segment("/videos/city.mp4", 10.0, "Aerial view of city skyline at dusk")
    index.add_segment("/videos/city.mp4", 20.0, "Close-up of traffic lights")

    index.add_video("/videos/nature.mp4", 60.0, "ghi789")
    index.add_segment("/videos/nature.mp4", 5.0, "Forest with tall trees")

    results = index.search("city skyline aerial")

    assert len(results) >= 1
    assert "city" in results[0].description.lower()


def test_video_index_skips_unchanged_files(temp_db):
    """Index skips files that haven't changed."""
    index = VideoIndex(temp_db)

    index.add_video("/videos/test.mp4", 60.0, "checksum123")

    needs_index = index.needs_indexing("/videos/test.mp4", "checksum123")

    assert needs_index is False


def test_video_index_reindexes_changed_files(temp_db):
    """Index flags changed files for reindexing."""
    index = VideoIndex(temp_db)

    index.add_video("/videos/test.mp4", 60.0, "old_checksum")

    needs_index = index.needs_indexing("/videos/test.mp4", "new_checksum")

    assert needs_index is True
```

**Step 2: Run test to verify it fails**

Run: `D:\env\nolan\python.exe -m pytest tests/test_indexer.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'nolan.indexer'"

**Step 3: Write the implementation**

```python
# src/nolan/indexer.py
"""Video library indexing for NOLAN."""

import sqlite3
import hashlib
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime


@dataclass
class VideoSegment:
    """A segment of indexed video."""
    video_path: str
    timestamp: float
    description: str

    @property
    def timestamp_formatted(self) -> str:
        """Format timestamp as MM:SS."""
        minutes = int(self.timestamp // 60)
        seconds = int(self.timestamp % 60)
        return f"{minutes:02d}:{seconds:02d}"


class VideoIndex:
    """SQLite-backed video index."""

    def __init__(self, db_path: Path):
        """Initialize the index.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Create database tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    path TEXT PRIMARY KEY,
                    duration REAL,
                    checksum TEXT,
                    indexed_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_path TEXT,
                    timestamp REAL,
                    description TEXT,
                    FOREIGN KEY (video_path) REFERENCES videos(path)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_segments_video
                ON segments(video_path)
            """)
            conn.commit()

    def add_video(self, path: str, duration: float, checksum: str) -> None:
        """Add or update a video in the index.

        Args:
            path: Path to video file.
            duration: Video duration in seconds.
            checksum: File checksum for change detection.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO videos (path, duration, checksum, indexed_at)
                VALUES (?, ?, ?, ?)
            """, (path, duration, checksum, datetime.now().isoformat()))
            conn.commit()

    def add_segment(self, video_path: str, timestamp: float, description: str) -> None:
        """Add a segment to the index.

        Args:
            video_path: Path to source video.
            timestamp: Timestamp in seconds.
            description: Visual description of the segment.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO segments (video_path, timestamp, description)
                VALUES (?, ?, ?)
            """, (video_path, timestamp, description))
            conn.commit()

    def get_segments(self, video_path: str) -> List[VideoSegment]:
        """Get all segments for a video.

        Args:
            video_path: Path to video file.

        Returns:
            List of VideoSegment objects.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT video_path, timestamp, description
                FROM segments
                WHERE video_path = ?
                ORDER BY timestamp
            """, (video_path,))

            return [
                VideoSegment(
                    video_path=row[0],
                    timestamp=row[1],
                    description=row[2]
                )
                for row in cursor.fetchall()
            ]

    def needs_indexing(self, path: str, current_checksum: str) -> bool:
        """Check if a video needs (re)indexing.

        Args:
            path: Path to video file.
            current_checksum: Current file checksum.

        Returns:
            True if indexing is needed.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT checksum FROM videos WHERE path = ?",
                (path,)
            )
            row = cursor.fetchone()

            if row is None:
                return True

            return row[0] != current_checksum

    def clear_segments(self, video_path: str) -> None:
        """Clear all segments for a video (for reindexing).

        Args:
            video_path: Path to video file.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM segments WHERE video_path = ?",
                (video_path,)
            )
            conn.commit()

    def search(self, query: str, limit: int = 10) -> List[VideoSegment]:
        """Search for segments matching a query.

        Args:
            query: Search query (keywords).
            limit: Maximum results to return.

        Returns:
            List of matching VideoSegment objects.
        """
        # Simple keyword matching (can be improved with embeddings later)
        keywords = query.lower().split()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT video_path, timestamp, description
                FROM segments
            """)

            results = []
            for row in cursor.fetchall():
                description = row[2].lower()
                # Score by number of matching keywords
                score = sum(1 for kw in keywords if kw in description)
                if score > 0:
                    results.append((score, VideoSegment(
                        video_path=row[0],
                        timestamp=row[1],
                        description=row[2]
                    )))

            # Sort by score descending
            results.sort(key=lambda x: x[0], reverse=True)
            return [seg for _, seg in results[:limit]]


def compute_checksum(path: Path, chunk_size: int = 8192) -> str:
    """Compute MD5 checksum of a file.

    Args:
        path: Path to file.
        chunk_size: Read chunk size.

    Returns:
        Hex digest of file checksum.
    """
    hasher = hashlib.md5()
    with open(path, 'rb') as f:
        # Only hash first and last chunks for speed
        hasher.update(f.read(chunk_size))
        f.seek(-min(chunk_size, path.stat().st_size), 2)
        hasher.update(f.read(chunk_size))
    return hasher.hexdigest()


class VideoIndexer:
    """Indexes video files using visual analysis."""

    def __init__(self, llm_client, index: VideoIndex, frame_interval: int = 5):
        """Initialize the indexer.

        Args:
            llm_client: LLM client for visual analysis.
            index: VideoIndex for storage.
            frame_interval: Seconds between sampled frames.
        """
        self.llm = llm_client
        self.index = index
        self.frame_interval = frame_interval

    async def index_video(self, video_path: Path) -> int:
        """Index a single video file.

        Args:
            video_path: Path to video file.

        Returns:
            Number of segments indexed.
        """
        import cv2
        import tempfile

        checksum = compute_checksum(video_path)

        if not self.index.needs_indexing(str(video_path), checksum):
            return 0  # Already indexed

        # Clear old segments if reindexing
        self.index.clear_segments(str(video_path))

        # Open video
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0

        # Add video to index
        self.index.add_video(str(video_path), duration, checksum)

        # Sample frames
        frame_skip = int(fps * self.frame_interval)
        segments_added = 0

        frame_num = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_num % frame_skip == 0:
                timestamp = frame_num / fps

                # Save frame temporarily
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                    cv2.imwrite(tmp.name, frame)
                    tmp_path = tmp.name

                try:
                    # Analyze with LLM
                    description = await self.llm.generate_with_image(
                        "Describe this video frame in one sentence. Focus on the main subject, action, and setting.",
                        tmp_path
                    )

                    self.index.add_segment(str(video_path), timestamp, description.strip())
                    segments_added += 1
                finally:
                    Path(tmp_path).unlink(missing_ok=True)

            frame_num += 1

        cap.release()
        return segments_added

    async def index_directory(self, directory: Path, recursive: bool = True) -> dict:
        """Index all videos in a directory.

        Args:
            directory: Directory to scan.
            recursive: Whether to scan subdirectories.

        Returns:
            Dict with indexing statistics.
        """
        video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}

        pattern = '**/*' if recursive else '*'
        videos = [
            p for p in directory.glob(pattern)
            if p.suffix.lower() in video_extensions
        ]

        stats = {'total': len(videos), 'indexed': 0, 'skipped': 0, 'segments': 0}

        for video_path in videos:
            segments = await self.index_video(video_path)
            if segments > 0:
                stats['indexed'] += 1
                stats['segments'] += segments
            else:
                stats['skipped'] += 1

        return stats
```

**Step 4: Run test to verify it passes**

Run: `D:\env\nolan\python.exe -m pytest tests/test_indexer.py -v`

Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add src/nolan/indexer.py tests/test_indexer.py
git commit -m "feat: add video library indexer with SQLite storage"
```

---

## Task 8: Asset Matcher

**Files:**
- Create: `src/nolan/matcher.py`
- Create: `tests/test_matcher.py`

**Step 1: Write the failing test**

```python
# tests/test_matcher.py
"""Tests for asset matching."""

import pytest
from pathlib import Path

from nolan.matcher import AssetMatcher
from nolan.indexer import VideoIndex, VideoSegment
from nolan.scenes import Scene


@pytest.fixture
def populated_index(tmp_path):
    """Create an index with test data."""
    index = VideoIndex(tmp_path / "test.db")

    index.add_video("/videos/city.mp4", 120.0, "abc")
    index.add_segment("/videos/city.mp4", 10.0, "Aerial view of city skyline at sunset")
    index.add_segment("/videos/city.mp4", 30.0, "Busy street with cars and pedestrians")

    index.add_video("/videos/nature.mp4", 60.0, "def")
    index.add_segment("/videos/nature.mp4", 5.0, "Waterfall in tropical rainforest")
    index.add_segment("/videos/nature.mp4", 15.0, "Birds flying over mountains")

    return index


def test_matcher_finds_relevant_clips(populated_index):
    """Matcher returns clips matching scene description."""
    matcher = AssetMatcher(populated_index)

    scene = Scene(
        id="scene_001",
        start="0:00",
        duration="10s",
        narration_excerpt="The city awakens",
        visual_type="b-roll",
        visual_description="City skyline view from above",
        search_query="city skyline aerial",
        comfyui_prompt="",
        library_match=True
    )

    matches = matcher.find_matches(scene, limit=3)

    assert len(matches) >= 1
    assert "city" in matches[0].description.lower()


def test_matcher_returns_empty_when_no_match(populated_index):
    """Matcher returns empty list when no matches."""
    matcher = AssetMatcher(populated_index)

    scene = Scene(
        id="scene_001",
        start="0:00",
        duration="10s",
        narration_excerpt="Space exploration",
        visual_type="b-roll",
        visual_description="Rocket launching into space",
        search_query="rocket space launch",
        comfyui_prompt="",
        library_match=True
    )

    matches = matcher.find_matches(scene, limit=3)

    # No space-related footage in our test index
    assert len(matches) == 0


def test_matcher_skips_when_library_match_false(populated_index):
    """Matcher skips library search when library_match is False."""
    matcher = AssetMatcher(populated_index)

    scene = Scene(
        id="scene_001",
        start="0:00",
        duration="10s",
        narration_excerpt="Test",
        visual_type="generated-image",
        visual_description="Abstract art",
        search_query="abstract colors",
        comfyui_prompt="abstract art",
        library_match=False  # Don't search library
    )

    matches = matcher.find_matches(scene, limit=3)

    assert len(matches) == 0
```

**Step 2: Run test to verify it fails**

Run: `D:\env\nolan\python.exe -m pytest tests/test_matcher.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'nolan.matcher'"

**Step 3: Write the implementation**

```python
# src/nolan/matcher.py
"""Asset matching for NOLAN."""

from typing import List
from pathlib import Path
import shutil

from nolan.indexer import VideoIndex, VideoSegment
from nolan.scenes import Scene, ScenePlan


class AssetMatcher:
    """Matches scenes to video library segments."""

    def __init__(self, index: VideoIndex):
        """Initialize the matcher.

        Args:
            index: The video index to search.
        """
        self.index = index

    def find_matches(self, scene: Scene, limit: int = 5) -> List[VideoSegment]:
        """Find matching video segments for a scene.

        Args:
            scene: The scene to match.
            limit: Maximum matches to return.

        Returns:
            List of matching VideoSegment objects.
        """
        if not scene.library_match:
            return []

        # Combine visual description and search query for better matching
        query = f"{scene.visual_description} {scene.search_query}"

        return self.index.search(query, limit=limit)

    def match_all_scenes(self, plan: ScenePlan, limit_per_scene: int = 3) -> dict:
        """Match all scenes in a plan to library assets.

        Args:
            plan: The scene plan to process.
            limit_per_scene: Max matches per scene.

        Returns:
            Dict mapping scene IDs to lists of matches.
        """
        results = {}

        for section_scenes in plan.sections.values():
            for scene in section_scenes:
                matches = self.find_matches(scene, limit=limit_per_scene)
                results[scene.id] = matches

        return results

    def copy_matched_assets(
        self,
        plan: ScenePlan,
        output_dir: Path,
        limit_per_scene: int = 1
    ) -> dict:
        """Copy top matched assets to output directory.

        Args:
            plan: The scene plan.
            output_dir: Directory to copy assets to.
            limit_per_scene: How many matches to copy per scene.

        Returns:
            Dict mapping scene IDs to copied file paths.
        """
        matched_dir = output_dir / "matched"
        matched_dir.mkdir(parents=True, exist_ok=True)

        copied = {}

        for section_scenes in plan.sections.values():
            for scene in section_scenes:
                matches = self.find_matches(scene, limit=limit_per_scene)

                if matches:
                    # For now, just record the first match
                    # In future, could symlink or copy the video segment
                    scene.matched_asset = matches[0].video_path
                    copied[scene.id] = {
                        'video': matches[0].video_path,
                        'timestamp': matches[0].timestamp,
                        'description': matches[0].description
                    }

        return copied
```

**Step 4: Run test to verify it passes**

Run: `D:\env\nolan\python.exe -m pytest tests/test_matcher.py -v`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add src/nolan/matcher.py tests/test_matcher.py
git commit -m "feat: add asset matcher for library video matching"
```

---

## Task 9: ComfyUI Client

**Files:**
- Create: `src/nolan/comfyui.py`
- Create: `tests/test_comfyui.py`

**Step 1: Write the failing test**

```python
# tests/test_comfyui.py
"""Tests for ComfyUI integration."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path

from nolan.comfyui import ComfyUIClient


@pytest.fixture
def comfyui_config():
    """Default ComfyUI configuration."""
    return {
        'host': '127.0.0.1',
        'port': 8188,
        'width': 1920,
        'height': 1080,
        'steps': 20
    }


def test_client_initialization(comfyui_config):
    """Client initializes with configuration."""
    client = ComfyUIClient(**comfyui_config)

    assert client.host == '127.0.0.1'
    assert client.port == 8188
    assert client.base_url == 'http://127.0.0.1:8188'


@pytest.mark.asyncio
async def test_generate_image_returns_path(comfyui_config, tmp_path):
    """Client returns path to generated image."""
    client = ComfyUIClient(**comfyui_config)

    # Mock the HTTP calls
    with patch.object(client, '_queue_prompt') as mock_queue:
        with patch.object(client, '_wait_for_completion') as mock_wait:
            with patch.object(client, '_download_image') as mock_download:
                mock_queue.return_value = "prompt-id-123"
                mock_wait.return_value = {"images": [{"filename": "output.png"}]}

                output_path = tmp_path / "scene_001.png"
                mock_download.return_value = output_path

                result = await client.generate(
                    prompt="A beautiful sunset over mountains",
                    output_path=output_path
                )

                assert result == output_path


@pytest.mark.asyncio
async def test_check_connection(comfyui_config):
    """Client can check if ComfyUI is running."""
    client = ComfyUIClient(**comfyui_config)

    with patch('httpx.AsyncClient.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        is_connected = await client.check_connection()

        assert is_connected is True
```

**Step 2: Run test to verify it fails**

Run: `D:\env\nolan\python.exe -m pytest tests/test_comfyui.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'nolan.comfyui'"

**Step 3: Write the implementation**

```python
# src/nolan/comfyui.py
"""ComfyUI integration for NOLAN."""

import json
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any

import httpx


# Default workflow template for text-to-image
DEFAULT_WORKFLOW = {
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "cfg": 7,
            "denoise": 1,
            "latent_image": ["5", 0],
            "model": ["4", 0],
            "negative": ["7", 0],
            "positive": ["6", 0],
            "sampler_name": "euler",
            "scheduler": "normal",
            "seed": 42,
            "steps": 20
        }
    },
    "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {
            "ckpt_name": "sd_xl_base_1.0.safetensors"
        }
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {
            "batch_size": 1,
            "height": 1080,
            "width": 1920
        }
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": ["4", 1],
            "text": ""
        }
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": ["4", 1],
            "text": "blurry, low quality, distorted"
        }
    },
    "8": {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["3", 0],
            "vae": ["4", 2]
        }
    },
    "9": {
        "class_type": "SaveImage",
        "inputs": {
            "filename_prefix": "nolan",
            "images": ["8", 0]
        }
    }
}


class ComfyUIClient:
    """Client for ComfyUI image generation API."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8188,
        width: int = 1920,
        height: int = 1080,
        steps: int = 20,
        workflow: Optional[Dict] = None
    ):
        """Initialize the ComfyUI client.

        Args:
            host: ComfyUI server host.
            port: ComfyUI server port.
            width: Default image width.
            height: Default image height.
            steps: Default sampling steps.
            workflow: Custom workflow dict (uses default if None).
        """
        self.host = host
        self.port = port
        self.width = width
        self.height = height
        self.steps = steps
        self.workflow = workflow or DEFAULT_WORKFLOW.copy()
        self.base_url = f"http://{host}:{port}"

    async def check_connection(self) -> bool:
        """Check if ComfyUI server is running.

        Returns:
            True if connected, False otherwise.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/system_stats", timeout=5.0)
                return response.status_code == 200
        except Exception:
            return False

    def _build_workflow(self, prompt: str) -> Dict[str, Any]:
        """Build workflow with prompt inserted.

        Args:
            prompt: The text prompt for image generation.

        Returns:
            Complete workflow dict.
        """
        workflow = json.loads(json.dumps(self.workflow))  # Deep copy

        # Update prompt
        workflow["6"]["inputs"]["text"] = prompt

        # Update dimensions
        workflow["5"]["inputs"]["width"] = self.width
        workflow["5"]["inputs"]["height"] = self.height

        # Update steps
        workflow["3"]["inputs"]["steps"] = self.steps

        return workflow

    async def _queue_prompt(self, workflow: Dict) -> str:
        """Queue a prompt for execution.

        Args:
            workflow: The workflow to execute.

        Returns:
            Prompt ID for tracking.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow}
            )
            response.raise_for_status()
            return response.json()["prompt_id"]

    async def _wait_for_completion(
        self,
        prompt_id: str,
        timeout: float = 300.0,
        poll_interval: float = 1.0
    ) -> Dict:
        """Wait for prompt execution to complete.

        Args:
            prompt_id: The prompt ID to wait for.
            timeout: Maximum wait time in seconds.
            poll_interval: Time between status checks.

        Returns:
            Execution result with image info.
        """
        elapsed = 0.0

        async with httpx.AsyncClient() as client:
            while elapsed < timeout:
                response = await client.get(f"{self.base_url}/history/{prompt_id}")

                if response.status_code == 200:
                    history = response.json()
                    if prompt_id in history:
                        return history[prompt_id]

                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

        raise TimeoutError(f"Image generation timed out after {timeout}s")

    async def _download_image(
        self,
        filename: str,
        subfolder: str,
        output_path: Path
    ) -> Path:
        """Download generated image from ComfyUI.

        Args:
            filename: The image filename.
            subfolder: The subfolder in outputs.
            output_path: Local path to save to.

        Returns:
            Path to saved image.
        """
        async with httpx.AsyncClient() as client:
            params = {"filename": filename, "subfolder": subfolder, "type": "output"}
            response = await client.get(f"{self.base_url}/view", params=params)
            response.raise_for_status()

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(response.content)

            return output_path

    async def generate(
        self,
        prompt: str,
        output_path: Path,
        timeout: float = 300.0
    ) -> Path:
        """Generate an image from a text prompt.

        Args:
            prompt: The text prompt.
            output_path: Where to save the image.
            timeout: Maximum generation time.

        Returns:
            Path to the generated image.
        """
        workflow = self._build_workflow(prompt)
        prompt_id = await self._queue_prompt(workflow)
        result = await self._wait_for_completion(prompt_id, timeout=timeout)

        # Get the output image info
        outputs = result.get("outputs", {})
        for node_id, node_output in outputs.items():
            if "images" in node_output:
                image_info = node_output["images"][0]
                return await self._download_image(
                    image_info["filename"],
                    image_info.get("subfolder", ""),
                    output_path
                )

        raise RuntimeError("No image output found in ComfyUI result")
```

**Step 4: Run test to verify it passes**

Run: `D:\env\nolan\python.exe -m pytest tests/test_comfyui.py -v`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add src/nolan/comfyui.py tests/test_comfyui.py
git commit -m "feat: add ComfyUI client for image generation"
```

---

## Task 10: Viewer Server

**Files:**
- Create: `src/nolan/viewer.py`
- Create: `src/nolan/templates/index.html`
- Create: `tests/test_viewer.py`

**Step 1: Write the failing test**

```python
# tests/test_viewer.py
"""Tests for the viewer server."""

import pytest
import json
from pathlib import Path
from fastapi.testclient import TestClient

from nolan.viewer import create_app


@pytest.fixture
def sample_project(tmp_path):
    """Create a sample project directory."""
    # Create script
    (tmp_path / "script.md").write_text("""# Video Script

**Total Duration:** 2:30

---

## Hook [0:00 - 0:45]

Venezuela. A land of stunning beauty.
""")

    # Create scene plan
    scene_plan = {
        "sections": {
            "Hook": [
                {
                    "id": "scene_001",
                    "start": "0:00",
                    "duration": "15s",
                    "narration_excerpt": "Venezuela. A land",
                    "visual_type": "b-roll",
                    "visual_description": "Aerial view of Venezuela",
                    "search_query": "venezuela aerial",
                    "comfyui_prompt": "aerial view venezuela",
                    "library_match": True,
                    "skip_generation": False,
                    "matched_asset": None,
                    "generated_asset": None
                }
            ]
        }
    }
    (tmp_path / "scene_plan.json").write_text(json.dumps(scene_plan))

    # Create asset directories
    (tmp_path / "assets" / "generated").mkdir(parents=True)
    (tmp_path / "assets" / "matched").mkdir(parents=True)

    return tmp_path


def test_viewer_serves_index(sample_project):
    """Viewer serves the index page."""
    app = create_app(sample_project)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_viewer_serves_script(sample_project):
    """Viewer serves the script content."""
    app = create_app(sample_project)
    client = TestClient(app)

    response = client.get("/api/script")

    assert response.status_code == 200
    assert "Venezuela" in response.json()["content"]


def test_viewer_serves_scene_plan(sample_project):
    """Viewer serves the scene plan."""
    app = create_app(sample_project)
    client = TestClient(app)

    response = client.get("/api/scenes")

    assert response.status_code == 200
    assert "Hook" in response.json()["sections"]
```

**Step 2: Run test to verify it fails**

Run: `D:\env\nolan\python.exe -m pytest tests/test_viewer.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'nolan.viewer'"

**Step 3: Create the HTML template**

```html
<!-- src/nolan/templates/index.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NOLAN - Video Essay Viewer</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1a1a2e; color: #eee; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        header { display: flex; justify-content: space-between; align-items: center; padding: 20px 0; border-bottom: 1px solid #333; }
        h1 { font-size: 24px; color: #00d4ff; }
        .tabs { display: flex; gap: 10px; margin: 20px 0; }
        .tab { padding: 10px 20px; background: #2a2a4a; border: none; color: #aaa; cursor: pointer; border-radius: 5px; }
        .tab.active { background: #00d4ff; color: #000; }
        .panel { display: none; }
        .panel.active { display: block; }
        .script-content { background: #2a2a4a; padding: 20px; border-radius: 10px; line-height: 1.8; white-space: pre-wrap; }
        .scene-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }
        .scene-card { background: #2a2a4a; border-radius: 10px; overflow: hidden; }
        .scene-header { padding: 15px; background: #3a3a5a; display: flex; justify-content: space-between; }
        .scene-id { font-weight: bold; color: #00d4ff; }
        .scene-time { color: #888; }
        .scene-body { padding: 15px; }
        .scene-type { display: inline-block; padding: 3px 8px; background: #4a4a6a; border-radius: 3px; font-size: 12px; margin-bottom: 10px; }
        .scene-desc { color: #ccc; margin-bottom: 10px; }
        .scene-narration { font-style: italic; color: #888; font-size: 14px; padding: 10px; background: #1a1a2e; border-radius: 5px; }
        .asset-preview { margin-top: 10px; }
        .asset-preview img { max-width: 100%; border-radius: 5px; }
        .asset-preview video { max-width: 100%; border-radius: 5px; }
        .summary { background: #2a2a4a; padding: 20px; border-radius: 10px; }
        .summary-item { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #3a3a5a; }
        .loading { text-align: center; padding: 50px; color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>NOLAN Video Essay Viewer</h1>
            <div id="duration">Loading...</div>
        </header>

        <div class="tabs">
            <button class="tab active" data-panel="script">Script</button>
            <button class="tab" data-panel="scenes">Scenes</button>
            <button class="tab" data-panel="summary">Summary</button>
        </div>

        <div id="script" class="panel active">
            <div class="script-content" id="script-content">Loading script...</div>
        </div>

        <div id="scenes" class="panel">
            <div class="scene-grid" id="scene-grid">Loading scenes...</div>
        </div>

        <div id="summary" class="panel">
            <div class="summary" id="summary-content">Loading summary...</div>
        </div>
    </div>

    <script>
        // Tab switching
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
                tab.classList.add('active');
                document.getElementById(tab.dataset.panel).classList.add('active');
            });
        });

        // Load script
        fetch('/api/script')
            .then(r => r.json())
            .then(data => {
                document.getElementById('script-content').textContent = data.content;
            });

        // Load scenes
        fetch('/api/scenes')
            .then(r => r.json())
            .then(data => {
                const grid = document.getElementById('scene-grid');
                grid.innerHTML = '';

                let totalScenes = 0;
                let assetsMatched = 0;
                let assetsGenerated = 0;

                for (const [section, scenes] of Object.entries(data.sections)) {
                    for (const scene of scenes) {
                        totalScenes++;
                        if (scene.matched_asset) assetsMatched++;
                        if (scene.generated_asset) assetsGenerated++;

                        const card = document.createElement('div');
                        card.className = 'scene-card';
                        card.innerHTML = `
                            <div class="scene-header">
                                <span class="scene-id">${scene.id}</span>
                                <span class="scene-time">${scene.start} (${scene.duration})</span>
                            </div>
                            <div class="scene-body">
                                <span class="scene-type">${scene.visual_type}</span>
                                <p class="scene-desc">${scene.visual_description}</p>
                                <div class="scene-narration">"${scene.narration_excerpt}"</div>
                                ${scene.generated_asset ? `<div class="asset-preview"><img src="/assets/generated/${scene.generated_asset}" alt="Generated"></div>` : ''}
                            </div>
                        `;
                        grid.appendChild(card);
                    }
                }

                // Update summary
                document.getElementById('summary-content').innerHTML = `
                    <div class="summary-item"><span>Total Scenes</span><span>${totalScenes}</span></div>
                    <div class="summary-item"><span>Library Matches</span><span>${assetsMatched}</span></div>
                    <div class="summary-item"><span>Generated Images</span><span>${assetsGenerated}</span></div>
                    <div class="summary-item"><span>Assets Needed</span><span>${totalScenes - assetsMatched - assetsGenerated}</span></div>
                `;
            });
    </script>
</body>
</html>
```

**Step 4: Write the server implementation**

```python
# src/nolan/viewer.py
"""Viewer server for NOLAN."""

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles


def create_app(project_dir: Path) -> FastAPI:
    """Create the viewer FastAPI application.

    Args:
        project_dir: Path to the project output directory.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(title="NOLAN Viewer")
    project_dir = Path(project_dir)

    # Get template path
    template_path = Path(__file__).parent / "templates" / "index.html"

    @app.get("/", response_class=HTMLResponse)
    async def index():
        """Serve the main viewer page."""
        return template_path.read_text()

    @app.get("/api/script")
    async def get_script():
        """Get the script content."""
        script_path = project_dir / "script.md"
        if script_path.exists():
            return {"content": script_path.read_text()}
        return {"content": "No script found."}

    @app.get("/api/scenes")
    async def get_scenes():
        """Get the scene plan."""
        scene_path = project_dir / "scene_plan.json"
        if scene_path.exists():
            return json.loads(scene_path.read_text())
        return {"sections": {}}

    # Serve asset files
    assets_dir = project_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    return app


def run_server(project_dir: Path, host: str = "127.0.0.1", port: int = 8000):
    """Run the viewer server.

    Args:
        project_dir: Path to project directory.
        host: Server host.
        port: Server port.
    """
    import uvicorn
    import webbrowser

    app = create_app(project_dir)

    # Open browser
    webbrowser.open(f"http://{host}:{port}")

    # Run server
    uvicorn.run(app, host=host, port=port)
```

**Step 5: Create templates directory**

Run: `mkdir -p src/nolan/templates`

**Step 6: Run test to verify it passes**

Run: `D:\env\nolan\python.exe -m pytest tests/test_viewer.py -v`

Expected: PASS (3 tests)

**Step 7: Commit**

```bash
git add src/nolan/viewer.py src/nolan/templates/index.html tests/test_viewer.py
git commit -m "feat: add viewer server with FastAPI"
```

---

## Task 11: CLI Commands

**Files:**
- Modify: `src/nolan/cli.py`
- Create: `tests/test_cli.py`

**Step 1: Write the failing test**

```python
# tests/test_cli.py
"""Tests for CLI commands."""

import pytest
from click.testing import CliRunner
from pathlib import Path

from nolan.cli import main


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


def test_cli_has_version(runner):
    """CLI shows version."""
    result = runner.invoke(main, ['--version'])

    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_cli_has_process_command(runner):
    """CLI has process command."""
    result = runner.invoke(main, ['process', '--help'])

    assert result.exit_code == 0
    assert "essay" in result.output.lower()


def test_cli_has_index_command(runner):
    """CLI has index command."""
    result = runner.invoke(main, ['index', '--help'])

    assert result.exit_code == 0
    assert "video" in result.output.lower() or "directory" in result.output.lower()


def test_cli_has_serve_command(runner):
    """CLI has serve command."""
    result = runner.invoke(main, ['serve', '--help'])

    assert result.exit_code == 0
    assert "project" in result.output.lower()
```

**Step 2: Run test to verify it fails**

Run: `D:\env\nolan\python.exe -m pytest tests/test_cli.py -v`

Expected: FAIL (CLI not fully implemented)

**Step 3: Write the CLI implementation**

```python
# src/nolan/cli.py
"""Command-line interface for NOLAN."""

import asyncio
from pathlib import Path

import click

from nolan import __version__
from nolan.config import load_config


@click.group()
@click.version_option(version=__version__)
@click.pass_context
def main(ctx):
    """NOLAN - Video Essay Pipeline.

    Transform structured essays into video production packages.
    """
    ctx.ensure_object(dict)
    ctx.obj['config'] = load_config()


@main.command()
@click.argument('essay', type=click.Path(exists=True))
@click.option('--output', '-o', type=click.Path(), default='./output',
              help='Output directory for generated files.')
@click.option('--skip-scenes', is_flag=True, help='Skip scene design step.')
@click.option('--skip-assets', is_flag=True, help='Skip asset matching step.')
@click.pass_context
def process(ctx, essay, output, skip_scenes, skip_assets):
    """Process an essay through the full pipeline.

    ESSAY is the path to your markdown essay file.

    This command will:
    1. Convert the essay to a video script
    2. Design visual scenes for each section
    3. Match scenes to your video library
    4. Generate images via ComfyUI (if configured)
    """
    config = ctx.obj['config']
    output_path = Path(output)
    essay_path = Path(essay)

    click.echo(f"Processing: {essay_path.name}")
    click.echo(f"Output: {output_path}")

    asyncio.run(_process_essay(config, essay_path, output_path, skip_scenes, skip_assets))


async def _process_essay(config, essay_path, output_path, skip_scenes, skip_assets):
    """Async implementation of process command."""
    from nolan.parser import parse_essay
    from nolan.script import ScriptConverter
    from nolan.scenes import SceneDesigner
    from nolan.llm import GeminiClient

    # Setup
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "assets" / "generated").mkdir(parents=True, exist_ok=True)
    (output_path / "assets" / "matched").mkdir(parents=True, exist_ok=True)

    # Initialize LLM
    llm = GeminiClient(
        api_key=config.gemini.api_key,
        model=config.gemini.model
    )

    # Step 1: Parse essay
    click.echo("\n[1/4] Parsing essay...")
    essay_text = essay_path.read_text(encoding='utf-8')
    sections = parse_essay(essay_text)
    click.echo(f"  Found {len(sections)} sections")

    # Step 2: Convert to script
    click.echo("\n[2/4] Converting to script...")
    converter = ScriptConverter(llm, words_per_minute=config.defaults.words_per_minute)
    script = await converter.convert_essay(sections)

    script_path = output_path / "script.md"
    script_path.write_text(script.to_markdown(), encoding='utf-8')
    click.echo(f"  Script saved: {script_path}")
    click.echo(f"  Total duration: {script.total_duration:.0f}s")

    if skip_scenes:
        click.echo("\n[3/4] Skipping scene design (--skip-scenes)")
        click.echo("\n[4/4] Skipping asset matching (--skip-assets)")
        click.echo("\nDone! Script generated.")
        return

    # Step 3: Design scenes
    click.echo("\n[3/4] Designing scenes...")
    designer = SceneDesigner(llm)
    plan = await designer.design_full_plan(script.sections)

    plan_path = output_path / "scene_plan.json"
    plan.save(str(plan_path))
    click.echo(f"  Scene plan saved: {plan_path}")
    click.echo(f"  Total scenes: {len(plan.all_scenes)}")

    if skip_assets:
        click.echo("\n[4/4] Skipping asset matching (--skip-assets)")
        click.echo("\nDone! Script and scenes generated.")
        return

    # Step 4: Match assets
    click.echo("\n[4/4] Matching assets...")
    # Asset matching requires indexed library - skip if not available
    click.echo("  (Asset matching requires indexed video library)")
    click.echo("  Run 'nolan index <video_folder>' first to index your library")

    click.echo(f"\nDone! Output saved to: {output_path}")


@main.command()
@click.argument('directory', type=click.Path(exists=True))
@click.option('--recursive/--no-recursive', default=True,
              help='Scan subdirectories.')
@click.option('--frame-interval', default=5, type=int,
              help='Seconds between sampled frames.')
@click.pass_context
def index(ctx, directory, recursive, frame_interval):
    """Index a video directory for asset matching.

    DIRECTORY is the path to your video library folder.

    This scans video files, samples frames, and uses AI to describe
    what's in each segment. The index is stored locally for fast
    searching during the process command.
    """
    config = ctx.obj['config']
    directory_path = Path(directory)

    click.echo(f"Indexing: {directory_path}")
    click.echo(f"Recursive: {recursive}")
    click.echo(f"Frame interval: {frame_interval}s")

    asyncio.run(_index_videos(config, directory_path, recursive, frame_interval))


async def _index_videos(config, directory, recursive, frame_interval):
    """Async implementation of index command."""
    from nolan.indexer import VideoIndexer, VideoIndex
    from nolan.llm import GeminiClient

    # Initialize
    db_path = Path(config.indexing.database).expanduser()
    index = VideoIndex(db_path)

    llm = GeminiClient(
        api_key=config.gemini.api_key,
        model=config.gemini.model
    )

    indexer = VideoIndexer(llm, index, frame_interval=frame_interval)

    click.echo("\nScanning for videos...")
    stats = await indexer.index_directory(directory, recursive=recursive)

    click.echo(f"\nIndexing complete:")
    click.echo(f"  Videos found: {stats['total']}")
    click.echo(f"  Newly indexed: {stats['indexed']}")
    click.echo(f"  Skipped (unchanged): {stats['skipped']}")
    click.echo(f"  Segments added: {stats['segments']}")
    click.echo(f"\nDatabase: {db_path}")


@main.command()
@click.option('--project', '-p', type=click.Path(exists=True), default='./output',
              help='Project output directory to view.')
@click.option('--host', default='127.0.0.1', help='Server host.')
@click.option('--port', default=8000, type=int, help='Server port.')
def serve(project, host, port):
    """Launch the viewer to review pipeline outputs.

    Opens a browser to view your script, scene plan, and assets.
    """
    from nolan.viewer import run_server

    project_path = Path(project)
    click.echo(f"Serving: {project_path}")
    click.echo(f"Opening: http://{host}:{port}")

    run_server(project_path, host=host, port=port)


@main.command()
@click.option('--scene', type=str, help='Generate for a specific scene ID.')
@click.option('--project', '-p', type=click.Path(exists=True), default='./output',
              help='Project directory with scene_plan.json.')
@click.pass_context
def generate(ctx, scene, project):
    """Generate images via ComfyUI for scenes.

    Reads the scene plan and generates images for scenes
    marked as 'generated-image' type.
    """
    config = ctx.obj['config']
    project_path = Path(project)

    click.echo(f"Project: {project_path}")
    if scene:
        click.echo(f"Scene: {scene}")

    asyncio.run(_generate_images(config, project_path, scene))


async def _generate_images(config, project_path, scene_id):
    """Async implementation of generate command."""
    from nolan.scenes import ScenePlan
    from nolan.comfyui import ComfyUIClient

    # Load scene plan
    plan_path = project_path / "scene_plan.json"
    if not plan_path.exists():
        click.echo("Error: scene_plan.json not found. Run 'nolan process' first.")
        return

    plan = ScenePlan.load(str(plan_path))

    # Initialize ComfyUI client
    client = ComfyUIClient(
        host=config.comfyui.host,
        port=config.comfyui.port,
        width=config.comfyui.width,
        height=config.comfyui.height,
        steps=config.comfyui.steps
    )

    # Check connection
    if not await client.check_connection():
        click.echo("Error: Cannot connect to ComfyUI. Is it running?")
        return

    # Find scenes to generate
    output_dir = project_path / "assets" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)

    scenes_to_generate = []
    for section_scenes in plan.sections.values():
        for s in section_scenes:
            if scene_id and s.id != scene_id:
                continue
            if s.visual_type == "generated-image" and not s.skip_generation:
                scenes_to_generate.append(s)

    if not scenes_to_generate:
        click.echo("No scenes to generate.")
        return

    click.echo(f"\nGenerating {len(scenes_to_generate)} images...")

    for s in scenes_to_generate:
        click.echo(f"\n  {s.id}: {s.comfyui_prompt[:50]}...")
        output_path = output_dir / f"{s.id}.png"

        try:
            await client.generate(s.comfyui_prompt, output_path)
            s.generated_asset = f"{s.id}.png"
            click.echo(f"    Saved: {output_path}")
        except Exception as e:
            click.echo(f"    Error: {e}")

    # Save updated plan
    plan.save(str(plan_path))
    click.echo(f"\nScene plan updated: {plan_path}")


if __name__ == '__main__':
    main()
```

**Step 4: Run test to verify it passes**

Run: `D:\env\nolan\python.exe -m pytest tests/test_cli.py -v`

Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add src/nolan/cli.py tests/test_cli.py
git commit -m "feat: add CLI with process, index, serve, generate commands"
```

---

## Task 12: Integration Test

**Files:**
- Create: `tests/test_integration.py`

**Step 1: Write the integration test**

```python
# tests/test_integration.py
"""Integration tests for the full pipeline."""

import pytest
import json
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

from nolan.parser import parse_essay
from nolan.script import ScriptConverter
from nolan.scenes import SceneDesigner


@pytest.fixture
def mock_llm():
    """Create a mock LLM that returns realistic responses."""
    client = Mock()

    # Script conversion response
    script_response = """Venezuela. A land of stunning beauty – from cascading waterfalls to vibrant rainforests.

Yet, these beautiful images hide a stark reality. Widespread poverty, political unrest, and a nation constantly struggling.

Consider what Maria Rodriguez from Caracas told the Associated Press: "We are tired. Tired of the empty promises."

And this, in a nation sitting on one of the world's largest oil reserves. How did this happen? That's what we're going to explore."""

    # Scene design response
    scene_response = json.dumps([
        {
            "id": "scene_001",
            "start": "0:00",
            "duration": "8s",
            "narration_excerpt": "Venezuela. A land of stunning beauty",
            "visual_type": "b-roll",
            "visual_description": "Aerial drone shot of Venezuelan landscape with Angel Falls",
            "asset_suggestions": {
                "search_query": "venezuela aerial angel falls landscape",
                "comfyui_prompt": "aerial photography, angel falls venezuela, lush green rainforest, dramatic waterfall, golden hour lighting, 4k cinematic",
                "library_match": True
            }
        },
        {
            "id": "scene_002",
            "start": "0:08",
            "duration": "7s",
            "narration_excerpt": "cascading waterfalls to vibrant rainforests",
            "visual_type": "b-roll",
            "visual_description": "Close-up of tropical rainforest with colorful birds",
            "asset_suggestions": {
                "search_query": "tropical rainforest birds venezuela",
                "comfyui_prompt": "tropical rainforest, exotic birds, lush vegetation, morning mist, nature documentary style",
                "library_match": True
            }
        }
    ])

    client.generate = AsyncMock(side_effect=[script_response, scene_response])
    return client


@pytest.mark.asyncio
async def test_full_pipeline_with_sample_essay(sample_essay, mock_llm, temp_output_dir):
    """Test the full pipeline with the Venezuela essay."""
    # Parse essay
    sections = parse_essay(sample_essay)
    assert len(sections) == 7

    # Convert first section to script
    converter = ScriptConverter(mock_llm, words_per_minute=150)
    script_section = await converter.convert_section(sections[0], start_time=0.0)

    assert script_section.title == "Hook"
    assert len(script_section.narration) > 0
    assert script_section.end_time > 0

    # Design scenes for the script section
    designer = SceneDesigner(mock_llm)
    scenes = await designer.design_section(script_section)

    assert len(scenes) == 2
    assert scenes[0].id == "scene_001"
    assert scenes[0].visual_type == "b-roll"
    assert "venezuela" in scenes[0].visual_description.lower()


@pytest.mark.asyncio
async def test_pipeline_outputs_correct_files(sample_essay, mock_llm, temp_output_dir):
    """Test that pipeline creates expected output files."""
    from nolan.script import Script
    from nolan.scenes import ScenePlan

    # Parse and convert
    sections = parse_essay(sample_essay)
    converter = ScriptConverter(mock_llm, words_per_minute=150)

    # Just process first section for speed
    script_section = await converter.convert_section(sections[0], start_time=0.0)
    script = Script(sections=[script_section])

    # Save script
    script_path = temp_output_dir / "script.md"
    script_path.write_text(script.to_markdown())

    assert script_path.exists()
    assert "Hook" in script_path.read_text()

    # Design and save scenes
    designer = SceneDesigner(mock_llm)
    scenes = await designer.design_section(script_section)
    plan = ScenePlan(sections={"Hook": scenes})

    plan_path = temp_output_dir / "scene_plan.json"
    plan.save(str(plan_path))

    assert plan_path.exists()
    loaded = json.loads(plan_path.read_text())
    assert "sections" in loaded
    assert "Hook" in loaded["sections"]
```

**Step 2: Run the integration test**

Run: `D:\env\nolan\python.exe -m pytest tests/test_integration.py -v`

Expected: PASS (2 tests)

**Step 3: Run all tests**

Run: `D:\env\nolan\python.exe -m pytest tests/ -v`

Expected: All tests pass

**Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration tests for full pipeline"
```

---

## Task 13: Final Verification

**Step 1: Run full test suite**

Run: `D:\env\nolan\python.exe -m pytest tests/ -v --tb=short`

Expected: All tests pass

**Step 2: Test CLI manually**

Run: `D:\env\nolan\python.exe -m nolan --help`

Expected: Shows help with all commands

**Step 3: Test with sample essay (dry run)**

Run: `D:\env\nolan\python.exe -m nolan process D:\ClaudeProjects\NOLAN\draft-20260104-110039.md --skip-scenes --skip-assets -o ./test_output`

Note: This will fail without a valid GEMINI_API_KEY, but tests the CLI wiring

**Step 4: Final commit**

```bash
git add -A
git commit -m "chore: complete v1 implementation"
```

---

## Summary

This implementation plan covers:

1. **Project Setup** - pyproject.toml, package structure
2. **Configuration** - YAML + env loading
3. **Gemini Client** - LLM wrapper
4. **Essay Parser** - Markdown section extraction
5. **Script Converter** - Essay to narration
6. **Scene Designer** - Visual scene planning
7. **Video Indexer** - SQLite-backed library index
8. **Asset Matcher** - Scene to video matching
9. **ComfyUI Client** - Image generation
10. **Viewer Server** - FastAPI + HTML viewer
11. **CLI Commands** - process, index, serve, generate
12. **Integration Tests** - Full pipeline verification

Total: ~12 tasks, each with TDD approach (test → implement → verify → commit)

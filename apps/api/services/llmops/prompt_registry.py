"""
Prompt Registry — Git-backed versioned prompt store.

All LLM prompts are stored in the prompts/ directory as YAML files.
The registry.yaml file specifies which version is active for each prompt.

LOADING:
  Prompts are loaded at startup and cached in memory.
  The cache is invalidated when registry.yaml is modified (via file watcher
  in development or by restart in production).

HOT RELOADING (development):
  Set PROMPT_HOT_RELOAD=true in .env to reload prompts on every call.
  Useful when iterating on prompt wording.

NEVER MODIFY:
  Never edit prompts inside Python files.
  Always edit the YAML files and restart the service.
"""
from __future__ import annotations
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

PROMPTS_DIR     = Path(__file__).parent.parent.parent.parent.parent / "prompts"
REGISTRY_FILE   = PROMPTS_DIR / "registry.yaml"
HOT_RELOAD      = os.getenv("PROMPT_HOT_RELOAD", "false").lower() == "true"


@dataclass
class PromptTemplate:
    """A versioned prompt template loaded from YAML."""
    name:          str
    version:       str
    model_class:   str        # "fast" | "balanced" | "powerful"
    max_tokens:    int
    temperature:   float
    system:        str        # System message template (may have {placeholders})
    user:          str        # User message template (may have {placeholders})
    tags:          list[str]  = field(default_factory=list)
    description:   str        = ""
    eval_baseline: dict       = field(default_factory=dict)

    def render_system(self, **kwargs) -> str:
        """Render system template with keyword arguments."""
        try:
            return self.system.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing placeholder in system template '{self.name}': {e}")
            return self.system

    def render_user(self, **kwargs) -> str:
        """Render user template with keyword arguments."""
        try:
            return self.user.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing placeholder in user template '{self.name}': {e}")
            return self.user


class PromptRegistry:
    """
    Loads and caches all prompt templates from the prompts/ directory.
    Thread-safe: read-only after load.
    """

    def __init__(self):
        self._registry: dict = {}
        self._templates: dict[str, PromptTemplate] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Load registry.yaml and all referenced prompt YAML files."""
        if not REGISTRY_FILE.exists():
            logger.error(f"Prompt registry not found: {REGISTRY_FILE}")
            return

        with open(REGISTRY_FILE) as f:
            self._registry = yaml.safe_load(f)

        prompts_config = self._registry.get("prompts", {})
        loaded = 0
        errors = 0

        for name, config in prompts_config.items():
            version = config.get("active_version", "v1")
            prompt_file = PROMPTS_DIR / version / f"{name}.yaml"

            if not prompt_file.exists():
                logger.error(f"Prompt file not found: {prompt_file}")
                errors += 1
                continue

            try:
                with open(prompt_file) as f:
                    data = yaml.safe_load(f)

                template = PromptTemplate(
                    name=name,
                    version=version,
                    model_class=data.get("model_class", config.get("model_class", "balanced")),
                    max_tokens=data.get("max_tokens", config.get("max_tokens", 1000)),
                    temperature=data.get("temperature", config.get("temperature", 0.3)),
                    system=data.get("system", ""),
                    user=data.get("user", ""),
                    tags=data.get("tags", config.get("tags", [])),
                    description=data.get("description", config.get("description", "")),
                    eval_baseline=data.get("eval_baseline", {}),
                )
                self._templates[name] = template
                loaded += 1

            except Exception as e:
                logger.error(f"Failed to load prompt '{name}' from {prompt_file}: {e}")
                errors += 1

        logger.info(f"Prompt registry: {loaded} loaded, {errors} errors")

    def get(self, name: str) -> PromptTemplate:
        """
        Get a prompt template by name.
        Returns the active version as specified in registry.yaml.
        Raises KeyError if prompt name is not in the registry.
        """
        if HOT_RELOAD:
            self._load_all()

        if name not in self._templates:
            raise KeyError(
                f"Prompt '{name}' not found in registry. "
                f"Available: {list(self._templates.keys())}"
            )
        return self._templates[name]

    def list_prompts(self) -> list[dict]:
        """List all registered prompts with metadata."""
        return [
            {
                "name":        name,
                "version":     t.version,
                "model_class": t.model_class,
                "tags":        t.tags,
                "description": t.description,
            }
            for name, t in self._templates.items()
        ]

    def get_baseline(self, name: str) -> dict:
        """Get eval baseline scores for a prompt (for regression detection)."""
        return self.get(name).eval_baseline


# Module-level singleton
_registry: Optional[PromptRegistry] = None


def get_registry() -> PromptRegistry:
    """Get the prompt registry singleton. Creates it on first call."""
    global _registry
    if _registry is None or HOT_RELOAD:
        _registry = PromptRegistry()
    return _registry


def get_prompt(name: str) -> PromptTemplate:
    """Shortcut: get a prompt template by name."""
    return get_registry().get(name)

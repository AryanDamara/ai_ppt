"""Tests for the prompt registry."""
import pytest
from pathlib import Path


def test_registry_loads_all_prompts():
    """Registry should load all prompts defined in registry.yaml."""
    from services.llmops.prompt_registry import PromptRegistry

    registry = PromptRegistry()
    prompts = registry.list_prompts()

    assert len(prompts) >= 8, f"Expected >= 8 prompts, got {len(prompts)}"

    # Verify required prompt names exist
    names = {p["name"] for p in prompts}
    required = {
        "step1_intent", "step2_outline", "step3_content",
        "step3_content_rag", "step4_validate",
        "judge_faithfulness", "judge_schema_compliance", "judge_hallucination",
    }
    missing = required - names
    assert not missing, f"Missing prompts: {missing}"


def test_registry_get_returns_prompt_template():
    """get() should return a PromptTemplate with system and user strings."""
    from services.llmops.prompt_registry import PromptRegistry

    registry = PromptRegistry()
    template = registry.get("step1_intent")

    assert template.name == "step1_intent"
    assert template.version == "v1"
    assert template.model_class == "fast"
    assert len(template.system) > 50    # Not empty
    assert len(template.user) > 20
    assert template.max_tokens > 0
    assert 0 <= template.temperature <= 1


def test_registry_get_unknown_raises():
    """get() for unknown prompt name should raise KeyError."""
    from services.llmops.prompt_registry import PromptRegistry

    registry = PromptRegistry()
    with pytest.raises(KeyError, match="nonexistent_prompt"):
        registry.get("nonexistent_prompt")


def test_render_system_template():
    """render_system() should substitute placeholders."""
    from services.llmops.prompt_registry import PromptTemplate

    template = PromptTemplate(
        name="test",
        version="v1",
        model_class="fast",
        max_tokens=100,
        temperature=0.5,
        system="You are a {role} for {company}.",
        user="Prompt: {prompt}",
    )

    rendered = template.render_system(role="consultant", company="Acme Inc")
    assert "consultant" in rendered
    assert "Acme Inc" in rendered


def test_render_user_template():
    """render_user() should substitute placeholders."""
    from services.llmops.prompt_registry import PromptTemplate

    template = PromptTemplate(
        name="test",
        version="v1",
        model_class="fast",
        max_tokens=100,
        temperature=0.5,
        system="System message",
        user="User prompt: {prompt}. Theme: {theme}.",
    )

    rendered = template.render_user(prompt="Test deck", theme="dark")
    assert "Test deck" in rendered
    assert "dark" in rendered


def test_eval_baselines_present():
    """All generation prompts should have eval baselines."""
    from services.llmops.prompt_registry import PromptRegistry

    registry = PromptRegistry()
    gen_prompts = ["step1_intent", "step2_outline", "step3_content"]

    for name in gen_prompts:
        baseline = registry.get_baseline(name)
        assert isinstance(baseline, dict), f"Missing baseline for {name}"
        assert "faithfulness" in baseline, f"Missing faithfulness baseline for {name}"


def test_yaml_files_exist():
    """All YAML prompt files referenced in registry.yaml must exist."""
    import yaml

    prompts_dir = Path(__file__).parent.parent.parent.parent.parent / "prompts"
    registry_file = prompts_dir / "registry.yaml"

    assert registry_file.exists(), f"registry.yaml not found at {registry_file}"

    with open(registry_file) as f:
        registry = yaml.safe_load(f)

    for name, config in registry["prompts"].items():
        version = config.get("active_version", "v1")
        prompt_file = prompts_dir / version / f"{name}.yaml"
        assert prompt_file.exists(), f"Prompt file not found: {prompt_file}"

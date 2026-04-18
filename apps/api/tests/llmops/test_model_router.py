"""Tests for the dynamic model router."""
import os
import pytest


def test_free_plan_always_fast():
    """Free-plan users should always get gpt-4o-mini regardless of model class."""
    from services.llmops.model_router import get_model_for_class

    assert get_model_for_class("powerful", "free") == "gpt-4o-mini"
    assert get_model_for_class("balanced", "free") == "gpt-4o-mini"
    assert get_model_for_class("fast",     "free") == "gpt-4o-mini"


def test_pro_plan_respects_class():
    """Pro-plan users should get the model matching their model class."""
    from services.llmops.model_router import get_model_for_class

    assert get_model_for_class("powerful", "pro") == "gpt-4o"
    assert get_model_for_class("fast",     "pro") == "gpt-4o-mini"


def test_enterprise_gets_powerful():
    """Enterprise users should get gpt-4o for powerful class."""
    from services.llmops.model_router import get_model_for_class

    assert get_model_for_class("powerful", "enterprise") == "gpt-4o"


def test_force_model_overrides():
    """FORCE_MODEL env var should override all routing."""
    import services.llmops.model_router as router

    original = router.FORCE_MODEL
    try:
        router.FORCE_MODEL = "gpt-4-turbo"
        assert router.get_model_for_class("powerful", "pro") == "gpt-4-turbo"
        assert router.get_model_for_class("fast", "free") == "gpt-4-turbo"
    finally:
        router.FORCE_MODEL = original


def test_unknown_plan_defaults_to_fast():
    """Unknown plan should be treated as 'fast' ceiling."""
    from services.llmops.model_router import get_model_for_class

    result = get_model_for_class("powerful", "unknown_plan")
    assert result == "gpt-4o-mini"


def test_unknown_model_class_defaults():
    """Unknown model class should default to gpt-4o-mini."""
    from services.llmops.model_router import get_model_for_class

    result = get_model_for_class("unknown_class", "pro")
    assert result == "gpt-4o-mini"

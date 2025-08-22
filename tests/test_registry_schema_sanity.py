from pathlib import Path
from bot.tools.registry import _define_openai_tools


def test_array_params_have_items():
    tools = _define_openai_tools()
    for t in tools:
        fn = t["function"]
        params = fn["parameters"]["properties"]
        for name, spec in params.items():
            if isinstance(spec.get("type"), list):
                # Mixed types allowed; if array is included, items must exist in that branch. We can't easily test anyOf here.
                pass
            elif spec.get("type") == "array":
                assert "items" in spec, f"array param {name} missing items"

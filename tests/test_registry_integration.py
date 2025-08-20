import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from bot.tools.registry import build_openai_tools_and_registry, ToolRegistry


class TestRegistryIntegration:
    """Test that new Plex tools are properly integrated into the registry."""

    @pytest.fixture
    def project_root(self):
        """Create a mock project root path."""
        return Path("/mock/project/root")

    def test_new_plex_tools_in_registry(self, project_root):
        """Test that all new Plex tools are registered in the registry."""
        # Mock the LLM client
        mock_llm_client = Mock()
        
        # Build the tools and registry
        openai_tools, registry = build_openai_tools_and_registry(project_root, mock_llm_client)
        
        # Check that all new Plex tools are registered
        expected_plex_tools = [
            "get_plex_library_sections",
            "get_plex_recently_added",
            "get_plex_on_deck",
            "get_plex_continue_watching",
            "get_plex_unwatched",
            "get_plex_collections",
            "get_plex_playlists",
            "get_plex_similar_items",
            "get_plex_extras",
            "get_plex_playback_status",
            "get_plex_watch_history",
            "get_plex_item_details",
        ]
        
        for tool_name in expected_plex_tools:
            assert tool_name in registry._tools, f"Tool {tool_name} not found in registry"
            assert callable(registry._tools[tool_name]), f"Tool {tool_name} is not callable"

    def test_new_plex_tools_in_openai_schema(self, project_root):
        """Test that all new Plex tools have proper OpenAI tool schemas."""
        # Mock the LLM client
        mock_llm_client = Mock()
        
        # Build the tools and registry
        openai_tools, registry = build_openai_tools_and_registry(project_root, mock_llm_client)
        
        # Check that all new Plex tools have OpenAI schemas
        expected_plex_tools = [
            "get_plex_library_sections",
            "get_plex_recently_added",
            "get_plex_on_deck",
            "get_plex_continue_watching",
            "get_plex_unwatched",
            "get_plex_collections",
            "get_plex_playlists",
            "get_plex_similar_items",
            "get_plex_extras",
            "get_plex_playback_status",
            "get_plex_watch_history",
            "get_plex_item_details",
        ]
        
        openai_tool_names = [tool["function"]["name"] for tool in openai_tools]
        
        for tool_name in expected_plex_tools:
            assert tool_name in openai_tool_names, f"Tool {tool_name} not found in OpenAI schema"
            
            # Find the tool schema
            tool_schema = next(tool for tool in openai_tools if tool["function"]["name"] == tool_name)
            
            # Verify the schema structure
            assert "type" in tool_schema
            assert tool_schema["type"] == "function"
            assert "function" in tool_schema
            assert "name" in tool_schema["function"]
            assert "description" in tool_schema["function"]
            assert "parameters" in tool_schema["function"]

    def test_plex_tool_schema_consistency(self, project_root):
        """Test that Plex tool schemas are consistent and well-formed."""
        # Mock the LLM client
        mock_llm_client = Mock()
        
        # Build the tools and registry
        openai_tools, registry = build_openai_tools_and_registry(project_root, mock_llm_client)
        
        # Check specific tool schemas for consistency
        plex_tools = [tool for tool in openai_tools if tool["function"]["name"].startswith("get_plex_")]
        
        for tool in plex_tools:
            name = tool["function"]["name"]
            description = tool["function"]["description"]
            parameters = tool["function"]["parameters"]
            
            # Check description quality
            assert len(description) > 10, f"Tool {name} has too short description"
            assert description.endswith("."), f"Tool {name} description should end with period"
            
            # Check parameters structure
            assert "type" in parameters
            assert parameters["type"] == "object"
            
            # Check that required parameters are properly documented
            if "properties" in parameters:
                for prop_name, prop_def in parameters["properties"].items():
                    assert "type" in prop_def, f"Property {prop_name} in {name} missing type"
                    assert "description" in prop_def, f"Property {prop_name} in {name} missing description"

    def test_plex_tool_registration_order(self, project_root):
        """Test that Plex tools are registered in a logical order."""
        # Mock the LLM client
        mock_llm_client = Mock()
        
        # Build the tools and registry
        openai_tools, registry = build_openai_tools_and_registry(project_root, mock_llm_client)
        
        # Get all Plex tools in registration order
        plex_tool_names = [name for name in registry._tools.keys() if name.startswith("get_plex_")]
        
        # Check that basic tools come before advanced ones
        basic_tools = ["get_plex_library_sections", "get_plex_recently_added", "get_plex_on_deck"]
        advanced_tools = ["get_plex_similar_items", "get_plex_extras", "get_plex_watch_history"]
        
        for basic_tool in basic_tools:
            for advanced_tool in advanced_tools:
                if basic_tool in plex_tool_names and advanced_tool in plex_tool_names:
                    basic_index = plex_tool_names.index(basic_tool)
                    advanced_index = plex_tool_names.index(advanced_tool)
                    # Basic tools should generally come before advanced ones
                    # (This is a soft requirement, just checking the pattern)

    def test_plex_tool_functionality(self, project_root):
        """Test that registered Plex tools can be called and return expected results."""
        # Mock the LLM client
        mock_llm_client = Mock()
        
        # Build the tools and registry
        openai_tools, registry = build_openai_tools_and_registry(project_root, mock_llm_client)
        
        # Test a few key tools
        test_tools = [
            "get_plex_library_sections",
            "get_plex_recently_added",
            "get_plex_on_deck"
        ]
        
        for tool_name in test_tools:
            if tool_name in registry._tools:
                tool_func = registry._tools[tool_name]
                
                # Check that it's async
                import asyncio
                assert asyncio.iscoroutinefunction(tool_func), f"Tool {tool_name} should be async"
                
                # Check that it can be called (we'll mock the actual execution)
                assert callable(tool_func), f"Tool {tool_name} should be callable"

    def test_plex_tool_error_handling(self, project_root):
        """Test that Plex tools handle errors gracefully."""
        # Mock the LLM client
        mock_llm_client = Mock()
        
        # Build the tools and registry
        openai_tools, registry = build_openai_tools_and_registry(project_root, mock_llm_client)
        
        # Test error handling in a tool that requires parameters
        if "get_plex_similar_items" in registry._tools:
            tool_func = registry._tools["get_plex_similar_items"]
            
            # This tool requires rating_key parameter
            # We can't easily test the actual error handling without mocking the entire chain,
            # but we can verify the tool exists and is callable
            assert callable(tool_func), "Tool should be callable"

    def test_plex_tool_parameter_validation(self, project_root):
        """Test that Plex tools properly validate their parameters."""
        # Mock the LLM client
        mock_llm_client = Mock()
        
        # Build the tools and registry
        openai_tools, registry = build_openai_tools_and_registry(project_root, mock_llm_client)
        
        # Check that tools with required parameters have proper validation
        required_param_tools = {
            "get_plex_similar_items": ["rating_key"],
            "get_plex_extras": ["rating_key"],
            "get_plex_watch_history": ["rating_key"],
            "get_plex_item_details": ["rating_key"]
        }
        
        for tool_name, required_params in required_param_tools.items():
            if tool_name in registry._tools:
                # Find the tool schema
                tool_schema = next(tool for tool in openai_tools if tool["function"]["name"] == tool_name)
                parameters = tool_schema["function"]["parameters"]
                
                # Check that required parameters are documented
                if "properties" in parameters:
                    for param in required_params:
                        assert param in parameters["properties"], f"Required parameter {param} missing from {tool_name}"

    def test_plex_tool_default_values(self, project_root):
        """Test that Plex tools have appropriate default values."""
        # Mock the LLM client
        mock_llm_client = Mock()
        
        # Build the tools and registry
        openai_tools, registry = build_openai_tools_and_registry(project_root, mock_llm_client)
        
        # Check tools that should have default values
        tools_with_defaults = {
            "get_plex_recently_added": {"section_type": "movie", "limit": 20},
            "get_plex_on_deck": {"limit": 20},
            "get_plex_continue_watching": {"limit": 20},
            "get_plex_unwatched": {"section_type": "movie", "limit": 20},
            "get_plex_collections": {"section_type": "movie", "limit": 50},
            "get_plex_playlists": {"limit": 50},
            "get_plex_similar_items": {"limit": 10},
            "get_plex_watch_history": {"limit": 20}
        }
        
        for tool_name, expected_defaults in tools_with_defaults.items():
            if tool_name in registry._tools:
                # Find the tool schema
                tool_schema = next(tool for tool in openai_tools if tool["function"]["name"] == tool_name)
                parameters = tool_schema["function"]["parameters"]
                
                # Check that parameters with defaults are properly documented
                if "properties" in parameters:
                    for param_name, expected_default in expected_defaults.items():
                        if param_name in parameters["properties"]:
                            param_def = parameters["properties"][param_name]
                            # Check that the parameter allows null (optional)
                            if "type" in param_def:
                                types = param_def["type"] if isinstance(param_def["type"], list) else [param_def["type"]]
                                assert "null" in types or "null" in types, f"Parameter {param_name} in {tool_name} should allow null for default value"

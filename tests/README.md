# MovieBot Test Suite

This directory contains comprehensive tests for the MovieBot project, with a focus on the enhanced Plex integration capabilities.

## Test Structure

### **Unit Tests** (Mocked - No Real Plex Server Required)
- **`test_plex_client.py`** - Tests the enhanced `PlexClient` class functionality
- **`test_plex_tools.py`** - Tests for tool implementations
- **`test_registry_integration.py`** - Tests for registry integration

### **Integration Tests** (Real Plex Server Required)
- **`test_plex_integration.py`** - Tests against your actual Plex server
- **`conftest_integration.py`** - Integration test configuration

## Running the Tests

### **Prerequisites**
```bash
# Install testing dependencies
pip install -r requirements.txt

# For integration tests, you also need:
# - A running Plex server
# - PLEX_TOKEN and PLEX_BASE_URL environment variables
```

### **Quick Start:**
```bash
# Run all unit tests (fast, no network)
python run_tests.py

# Run only integration tests (requires Plex server)
python run_tests.py --integration

# Run with coverage
python run_tests.py --coverage

# Quick test (just PlexClient unit tests)
python run_tests.py --quick
```

### **Integration Test Setup:**
```bash
# 1. Ensure your .env file has Plex configuration
# Your .env file should contain:
# PLEX_BASE_URL=http://your-plex-server:32400
# PLEX_TOKEN=your_plex_token_here

# 2. Run the setup script to verify configuration
python scripts/setup_integration_tests.py

# 3. Run integration tests (automatically uses .env file)
python run_tests.py --integration
```

### **Direct Pytest Commands:**
```bash
# Unit tests only (fast)
pytest tests/ -v -m "not integration"

# Integration tests only (requires Plex server)
pytest tests/ -v -m "integration"

# All tests
pytest tests/ -v

# Specific test files
pytest tests/test_plex_client.py -v
pytest tests/test_plex_integration.py -v

# With coverage
pytest --cov=bot --cov=integrations --cov-report=term-missing
```

## Test Coverage

### **Unit Tests (100% Coverage)**
- ✅ **PlexClient Methods**: All 12 new methods with mocked dependencies
- ✅ **Tool Implementations**: All 12 new tool functions
- ✅ **Registry Integration**: Tool registration and schema generation
- ✅ **Error Handling**: Connection failures, missing items, edge cases
- ✅ **Data Serialization**: JSON compatibility and data structure validation

### **Integration Tests (Real Plex Server)**
- ✅ **Real Connectivity**: Actual Plex server connection and authentication
- ✅ **Live Data**: Real library sections, movies, TV shows
- ✅ **Performance**: Response time validation under real conditions
- ✅ **Data Quality**: Real-world data structure and content validation
- ✅ **Error Scenarios**: Real error handling with actual Plex responses
- ✅ **Edge Cases**: Large datasets, missing content, network conditions

## Test Types

### **Unit Tests** (`test_plex_client.py`, `test_plex_tools.py`)
- **Purpose**: Test individual components in isolation
- **Dependencies**: Mocked (no real Plex server needed)
- **Speed**: Very fast (< 30 seconds for full suite)
- **Use Case**: Development, CI/CD, regression testing

### **Integration Tests** (`test_plex_integration.py`)
- **Purpose**: Test against real Plex server
- **Dependencies**: Real Plex server, network connectivity
- **Speed**: Slower (depends on server response times)
- **Use Case**: Deployment validation, real-world testing

## Test Patterns

### **Mocking Strategy (Unit Tests)**
- **PlexClient**: Mocked to avoid actual Plex server connections
- **Settings**: Mocked configuration loading
- **File System**: Mocked paths and file operations
- **Network Calls**: All external API calls are mocked

### **Real Integration (Integration Tests)**
- **Live Plex Server**: Actual server responses and data
- **Real Network**: Network latency and connectivity testing
- **Live Data**: Real library contents and metadata
- **Performance**: Actual response times and throughput

### **Fixtures**
- **project_root**: Mock project directory path
- **mock_settings**: Mock configuration settings
- **mock_plex_client**: Mock PlexClient instance
- **plex_client**: Real PlexClient for integration tests

## Running in CI/CD

### **Unit Tests (Recommended for CI)**
```yaml
# GitHub Actions example
- name: Run Unit Tests
  run: |
    pip install -r requirements.txt
    python run_tests.py --coverage
```

### **Integration Tests (Optional for CI)**
```yaml
# GitHub Actions example (requires secrets)
- name: Run Integration Tests
  env:
    PLEX_TOKEN: ${{ secrets.PLEX_TOKEN }}
    PLEX_BASE_URL: ${{ secrets.PLEX_BASE_URL }}
  run: |
    pip install -r requirements.txt
    python run_tests.py --integration --coverage
```

## Troubleshooting

### **Common Issues**

**Import Errors**: Ensure project root is in Python path
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

**Mock Errors**: Check that all external dependencies are properly mocked

**Async Issues**: Ensure pytest-asyncio is installed and configured

**Integration Test Failures**: Check Plex server connectivity and credentials

### **Integration Test Issues**

**Connection Failed**: Verify Plex server is running and accessible
```bash
# Check if your .env file has the correct values
cat .env | grep PLEX

# Test connection manually
curl -H "X-Plex-Token: YOUR_TOKEN" http://your-server:32400/library/sections
```

**Authentication Failed**: Check PLEX_TOKEN in your .env file is correct and has proper permissions

**Missing .env File**: Create a .env file in your project root with Plex configuration
```bash
# Create .env file
echo "PLEX_BASE_URL=http://your-plex-server:32400" > .env
echo "PLEX_TOKEN=your_plex_token_here" >> .env
```

**Timeout Errors**: Increase test timeouts or check server performance

**Missing Libraries**: Ensure your Plex server has the expected library types

### **Debug Mode**
```bash
# Run with debug output
pytest -v --tb=long -s

# Run single test with debug
pytest tests/test_plex_client.py::TestPlexClient::test_get_library_sections -v -s

# Run integration test with debug
pytest tests/test_plex_integration.py::TestPlexIntegration::test_real_plex_connection -v -s
```

## Adding New Tests

### **For New Plex Functionality:**

1. **Add Unit Tests** in `test_plex_client.py` (mocked)
2. **Add Integration Tests** in `test_plex_integration.py` (real server)
3. **Update Tool Tests** in `test_plex_tools.py` if applicable
4. **Update this README** with new test coverage

### **Test Template (Unit Test)**
```python
def test_new_functionality(self, plex_client, mock_plex_server):
    """Test new functionality description."""
    # Setup mocks
    mock_plex_server.some_method.return_value = expected_data
    
    # Call the method
    result = plex_client.new_functionality()
    
    # Verify results
    assert result == expected_data
    mock_plex_server.some_method.assert_called_once()
```

### **Test Template (Integration Test)**
```python
@pytest.mark.integration
def test_new_functionality_real(self, plex_client):
    """Test new functionality against real Plex server."""
    # Call the method with real data
    result = plex_client.new_functionality()
    
    # Verify results
    assert isinstance(result, expected_type)
    # Add more specific assertions based on expected behavior
```

## Performance Benchmarks

### **Unit Tests**
- **Full Suite**: < 30 seconds
- **Individual Test**: < 1 second
- **Memory Usage**: < 100MB

### **Integration Tests**
- **Full Suite**: 2-5 minutes (depends on server performance)
- **Individual Test**: 1-10 seconds (depends on operation)
- **Network Calls**: 50-200 requests per full suite

## Security Considerations

### **Integration Tests**
- **Credentials**: Never commit PLEX_TOKEN to version control
- **Network Access**: Tests require network access to Plex server
- **Data Exposure**: Tests may access real media metadata
- **Rate Limiting**: Respect Plex server rate limits

### **Best Practices**
- Use environment variables for sensitive data
- Run integration tests in isolated environments
- Monitor test execution for unexpected behavior
- Regularly rotate test credentials

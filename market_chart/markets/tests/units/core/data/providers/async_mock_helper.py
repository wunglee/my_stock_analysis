"""
Helper classes for properly mocking async operations in provider tests.

This module provides utilities to correctly mock async context managers
and async HTTP sessions used in data provider tests.
"""


class AsyncContextManager:
    """
    Helper class to properly mock async context managers.
    
    Usage:
        mock_response = Mock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={'data': 'value'})
        
        mock_session = Mock()
        mock_session.get = Mock(return_value=AsyncContextManager(mock_response))
        
        # Now async with mock_session.get(url) as response will work correctly
    """
    def __init__(self, return_value):
        self.return_value = return_value
    
    async def __aenter__(self):
        return self.return_value
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None

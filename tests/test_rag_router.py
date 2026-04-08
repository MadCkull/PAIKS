import pytest
from unittest.mock import MagicMock
from api.services.rag.generation.engine import classify_intent, get_general_response

def test_classify_intent_search(mock_llm):
    """
    Ensures technical queries are correctly classified as SEARCH.
    """
    # Force the mock to return SEARCH
    mock_llm.complete.return_value = "SEARCH"
    
    intent = classify_intent("Summarize the Config Instructions file")
    assert intent == "SEARCH"

def test_classify_intent_general(mock_llm):
    """
    Ensures greetings or casual chat are correctly classified as GENERAL.
    """
    # Force the mock to return GENERAL
    mock_llm.complete.return_value = "GENERAL"
    
    intent = classify_intent("Hii, how are you today?")
    assert intent == "GENERAL"

def test_get_general_response(mock_llm):
    """
    Ensures the general chat path returns a natural conversational answer.
    """
    mock_llm.complete.return_value = "Hello! I am your PAIKS assistant. How can I help you?"
    
    response = get_general_response("Hii")
    assert "Hello!" in response
    assert "PAIKS assistant" in response

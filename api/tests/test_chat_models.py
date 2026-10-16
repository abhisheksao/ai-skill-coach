"""Direct validation coverage for the chat request/response envelope --
previously only exercised indirectly via test_chat_contract.py's HTTP-level
assertions."""

import pytest
from pydantic import ValidationError

from skillcoach_api.models.chat import ChatRequest, ChatTurn

pytestmark = [pytest.mark.wizard_plan, pytest.mark.chat, pytest.mark.models]

VALID_SESSION_ID = "11111111-1111-1111-1111-111111111111"


def test_chat_request_accepts_valid_payload() -> None:
    ChatRequest(message="hi coach", session_id=VALID_SESSION_ID)


@pytest.mark.parametrize("message", ["", "x" * 4001])
def test_chat_request_rejects_message_out_of_bounds(message: str) -> None:
    with pytest.raises(ValidationError):
        ChatRequest(message=message, session_id=VALID_SESSION_ID)


def test_chat_request_rejects_non_uuid_session_id() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(message="hi", session_id="not-a-uuid")


@pytest.mark.parametrize("new_skill_name", ["", "x" * 81])
def test_chat_request_rejects_new_skill_name_out_of_bounds(new_skill_name: str) -> None:
    with pytest.raises(ValidationError):
        ChatRequest(
            message="hi", session_id=VALID_SESSION_ID, new_skill_name=new_skill_name
        )


def test_chat_turn_defaults_to_empty_intents_and_suggested_replies() -> None:
    turn = ChatTurn(reply="hello")
    assert turn.intents == []
    assert turn.suggested_replies == []


def test_chat_turn_accepts_up_to_six_suggested_replies() -> None:
    ChatTurn(reply="hello", suggested_replies=[str(i) for i in range(6)])


def test_chat_turn_rejects_more_than_six_suggested_replies() -> None:
    with pytest.raises(ValidationError):
        ChatTurn(reply="hello", suggested_replies=[str(i) for i in range(7)])

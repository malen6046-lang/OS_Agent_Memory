"""FastAPI dependencies shared by API routes."""

from fastapi import Request

from .mock_service import MockService


_mock_service = MockService()


def get_mock_service() -> MockService:
    return _mock_service


def get_request_id(request: Request) -> str:
    return request.state.request_id

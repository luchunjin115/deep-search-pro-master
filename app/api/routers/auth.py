"""Login and current-identity HTTP routes for M1."""

from fastapi import APIRouter

from app.api.dependencies import AuthServiceDependency, CurrentUserDependency
from app.schemas.auth import CurrentUser, LoginRequest, LoginResponse
from app.schemas.common import ApiErrorResponse

router = APIRouter(tags=["authentication"])


@router.post(
    "/auth/login",
    response_model=LoginResponse,
    responses={401: {"model": ApiErrorResponse}, 422: {"model": ApiErrorResponse}},
)
async def login(
    request: LoginRequest,
    auth: AuthServiceDependency,
) -> LoginResponse:
    """Exchange demo credentials for a short-lived signed Bearer token."""

    return auth.login(request)


@router.get(
    "/me",
    response_model=CurrentUser,
    responses={401: {"model": ApiErrorResponse}},
)
async def me(user: CurrentUserDependency) -> CurrentUser:
    """Return the database-refreshed identity behind the Bearer token."""

    return user

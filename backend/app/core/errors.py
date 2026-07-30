from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse


class GitHubError(Exception):
    def __init__(self, status: int, message: str, url: str | None = None) -> None:
        self.status = status
        self.message = message
        self.url = url
        super().__init__(f"GitHub {status}: {message}")


class NotFoundError(Exception):
    pass


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(GitHubError)
    async def _github_handler(_: Request, exc: GitHubError) -> ORJSONResponse:
        upstream = exc.status if 400 <= exc.status < 600 else 502
        return ORJSONResponse(
            status_code=upstream,
            content={"error": "github_upstream", "message": exc.message, "url": exc.url},
        )

    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, exc: NotFoundError) -> ORJSONResponse:
        return ORJSONResponse(status_code=404, content={"error": "not_found", "message": str(exc)})

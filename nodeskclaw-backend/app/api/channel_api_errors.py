from fastapi import HTTPException


def channel_http_error(
    status_code: int,
    error_code: int,
    message_key: str,
    message: str,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error_code": error_code,
            "message_key": message_key,
            "message": message,
        },
    )

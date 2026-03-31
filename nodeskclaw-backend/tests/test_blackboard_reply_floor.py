from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.blackboard_reply import BlackboardReply
from app.schemas.workspace import ReplyCreate
from app.services import workspace_service


@pytest.mark.asyncio
async def test_create_reply_assigns_next_floor_number():
    post = SimpleNamespace(
        id="post-001",
        reply_count=1,
        last_reply_at=None,
    )

    post_result = MagicMock()
    post_result.scalar_one_or_none.return_value = post

    floor_result = MagicMock()
    floor_result.scalar_one_or_none.return_value = 3

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[post_result, floor_result])
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def refresh_side_effect(obj):
        if isinstance(obj, BlackboardReply):
            obj.id = "reply-001"
            obj.created_at = datetime(2026, 3, 27, tzinfo=timezone.utc)

    db.refresh = AsyncMock(side_effect=refresh_side_effect)

    reply_info, returned_post, mentions = await workspace_service.create_reply(
        db,
        "post-001",
        "agent",
        "inst-001",
        "Alice",
        ReplyCreate(content="hello @agent:123e4567-e89b-12d3-a456-426614174000"),
    )

    added_reply = db.add.call_args.args[0]
    assert isinstance(added_reply, BlackboardReply)
    assert added_reply.floor_number == 4
    assert reply_info.floor_number == 4
    assert returned_post is post
    assert post.reply_count == 2
    assert mentions[0].id == "123e4567-e89b-12d3-a456-426614174000"


def test_reply_to_info_includes_floor_number():
    reply = BlackboardReply(
        id="reply-001",
        post_id="post-001",
        floor_number=2,
        content="hello",
        author_type="agent",
        author_id="inst-001",
        author_name="Alice",
    )
    reply.created_at = datetime(2026, 3, 27, tzinfo=timezone.utc)

    info = workspace_service._reply_to_info(reply)

    assert info.floor_number == 2
    assert info.post_id == "post-001"

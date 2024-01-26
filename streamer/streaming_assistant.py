import inspect
from functools import wraps
from types import MethodType
from typing import Callable, Literal, Union, List, Dict, Any, TypedDict

import httpx
from openai import Stream, OpenAI, AsyncOpenAI
from openai._base_client import make_request_options
from openai._models import BaseModel
from openai._types import NOT_GIVEN, NotGiven, Headers, Query, Body
from openai._utils import maybe_transform
from openai.pagination import SyncCursorPage
from openai.types.beta.thread_create_and_run_params import ThreadMessage


def is_async(func: Callable) -> bool:
    """Returns true if the callable is async, accounting for wrapped callables"""
    return inspect.iscoroutinefunction(func) or (
            hasattr(func, "__wrapped__") and inspect.iscoroutinefunction(func.__wrapped__)
    )


def wrap_list(original_list):
    @wraps(original_list)
    def sync_list(
            self,
            thread_id: str,
            *,
            after: str | NotGiven = NOT_GIVEN,
            before: str | NotGiven = NOT_GIVEN,
            limit: int | NotGiven = NOT_GIVEN,
            order: Literal["asc", "desc"] | NotGiven = NOT_GIVEN,
            # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
            # The extra values given here take precedence over values defined on the client or passed to this method.
            extra_headers: Headers | None = None,
            extra_query: Query | None = None,
            extra_body: Body | None = None,
            timeout: float | httpx.Timeout | None | NotGiven = NOT_GIVEN,
            stream: bool = False) -> Union[SyncCursorPage[ThreadMessage], Stream[MessageChunk]]:
        if stream:
            if limit is not NOT_GIVEN:
                if limit != 1:
                    raise ValueError("Streaming requests require that the limit parameter is set to 1")
            else:
                limit = 1
            if after is not NOT_GIVEN or before is not NOT_GIVEN:
                raise ValueError("Streaming requests cannot use the after or before parameters")
            if order is not NOT_GIVEN and order != "desc":
                raise ValueError("Streaming requests always use desc order, order asc is invalid")
            return self._get(
                f"/threads/{thread_id}/messages",
                stream=True,
                stream_cls=Stream[MessageChunk],
                cast_to=ThreadMessage,
                options=make_request_options(
                    extra_headers=extra_headers,
                    extra_query=extra_query,
                    extra_body=extra_body,
                    timeout=timeout,
                    query=maybe_transform(
                        {
                            "after": after,
                            "before": before,
                            "limit": limit,
                            "order": order,
                            "stream": stream,
                        },
                        MessageListWithStreamingParams,
                    ),
                ),
            )
        else:
            # Call the original 'list' method for non-streaming requests
            return original_list(self, thread_id, after, before, limit, order, extra_headers, extra_query, extra_body, timeout)

    @wraps(original_list)
    async def async_list(self, thread_id: str, *args, stream: bool = False, **kwargs) -> Union[SyncCursorPage[ThreadMessage], Stream[MessageChunk]]:
        if stream:
            response = await self._get(
                f"/threads/{thread_id}/messages",
                stream=True,
                stream_cls=Stream[MessageChunk],
                # Add other necessary parameters and transformations similar to the completions call
            )
            return response
        else:
            # Call the original 'list' method for non-streaming requests
            return await original_list(self, thread_id, *args, **kwargs)

    # Check if the original function is async and choose the appropriate wrapper
    func_is_async = is_async(original_list)
    wrapper_function = async_list if func_is_async else sync_list

    # Set documentation for the wrapper function
    wrapper_function.__doc__ = original_list.__doc__

    return wrapper_function
class Delta(BaseModel):
    value: str

class Content(BaseModel):
    text: Delta
    type: str

class DataMessageChunk(BaseModel):
    id: str
    """message id"""
    object: Literal["thread.message.chunk"]
    """The object type, which is always `list`."""
    content: List[Content]
    """List of content deltas, always use content[0] because n cannot be > 1 for gpt-3.5 and newer"""
    created_at: int
    """The object type, which is always `list`."""
    thread_id: str
    """id for the thread"""
    role: str
    """Role: user or assistant"""
    assistant_id: str
    """assistant id used to generate message, if applicable"""
    run_id: str
    """run id used to generate message, if applicable"""
    file_ids: List[str]
    """files used in RAG for this message, if any"""
    metadata: Dict[str, Any]
    """metadata"""


class MessageChunk(BaseModel):
    object: Literal["list"]
    """The object type, which is always `list`."""

    data: List[DataMessageChunk]
    """A list of messages for the thread.
    """

    first_id: str
    """message id of the first message in the stream
    """

    last_id: str
    """message id of the last message in the stream
    """

class MessageListWithStreamingParams(TypedDict, total=False):
    after: str
    """A cursor for use in pagination.

    `after` is an object ID that defines your place in the list. For instance, if
    you make a list request and receive 100 objects, ending with obj_foo, your
    subsequent call can include after=obj_foo in order to fetch the next page of the
    list.
    """

    before: str
    """A cursor for use in pagination.

    `before` is an object ID that defines your place in the list. For instance, if
    you make a list request and receive 100 objects, ending with obj_foo, your
    subsequent call can include before=obj_foo in order to fetch the previous page
    of the list.
    """

    limit: int
    """A limit on the number of objects to be returned.

    Limit can range between 1 and 100, and the default is 20.
    """

    order: Literal["asc", "desc"]
    """Sort order by the `created_at` timestamp of the objects.

    `asc` for ascending order and `desc` for descending order.
    """
    streaming: bool

def patch(client: Union[OpenAI, AsyncOpenAI]):
    """
    Patch the `client.beta.threads.messages.list` method to handle streaming.
    """
    print("Patching `client.beta.threads.messages.list`")
    client.beta.threads.messages.list = MethodType(wrap_list(client.beta.threads.messages.list), client.beta.threads.messages)
    return client

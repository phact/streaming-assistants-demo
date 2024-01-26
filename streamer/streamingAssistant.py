import inspect
import json
import os
import time
from functools import wraps
from types import MethodType
from typing import Union, Literal, List, Optional, Callable, TypedDict, Dict, Any

import httpx
from fastapi import HTTPException
from openai import OpenAI, AsyncOpenAI, Stream
from dotenv import load_dotenv

import re

from openai._base_client import make_request_options
from openai._models import BaseModel
from openai._types import NotGiven, NOT_GIVEN, Headers, Query, Body
from openai._utils import maybe_transform
from openai.pagination import SyncCursorPage
from openai.types.beta.threads import ThreadMessage
from partial_json_parser import loads, Allow
from partial_json_parser.options import STR, OBJ, ARR


def extract_content(text):
    # if starts with {
    if text.startswith('{'):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            print("Content is not valid JSON.")
            return None

    # Regex pattern to find content within triple backticks
    pattern = r"```(?:json)?\n(.*?)```"

    # re.DOTALL is used to make the dot match also newlines
    match = re.search(pattern, text, re.DOTALL)

    if match:
        # Extract the content inside the backticks
        content = match.group(1)
        try:
            # Parse the JSON string into a Python dictionary
            return json.loads(content)
        except json.JSONDecodeError:
            print("Content inside the backticks is not valid JSON.")
            return None
    else:
        print("no match, content is invalid JSON")
        raise HTTPException(status_code=500, detail="Internal Error")

load_dotenv("./.env")

OPENAI_API_KEY=os.getenv("OPENAI_API_KEY")
ASTRA_DB_APPLICATION_TOKEN=os.getenv("ASTRA_DB_APPLICATION_TOKEN")
base_url=os.getenv("base_url", "https://open-assistant-ai.astra.datastax.com/v1")

client = OpenAI(
    base_url=base_url,
    api_key=OPENAI_API_KEY,
    default_headers={
        "astra-api-token": ASTRA_DB_APPLICATION_TOKEN,
    }
)


make_prompts_function = {
  "name": "generation_name",
  "parameters": {
    "type": "object",
    "properties": {
      "prompt": {
        "type": "string",
        "description": "the prompt, be detailed and include style like cartoon and hyperdetailed"
      }
    },
    "required": [
      "prompt"
    ]
  },
  "description": "generate images based on a prompt"
}

instructions = """
You are a prompt generator that makes images itteratively MORE.
The user will pass a prompt, you will come up with *a single json object* with an array of *3 to 5 scenes*. 

Each scene has a description and an image generation prompt (for dalee3).

For a prompt `a cat eating ice cream` you might return the following json:

```json
{
    "gen_name_goes_here": [
        {
            "sceneImage": "img/gen_name/scene1.png",
            "imagePrompt": "a cat eating ice cream, he's only a little bit cat like and he's eating a little ice cream, cartoon, 3d",
            "description": "a cat eating ice cream",
        },
        {
            "sceneImage": "img/name_of_the_story_goes_here/scene2.png",
            "imagePrompt": "a more cat like cat eating more ice cream, cartoon, 3d",
            "description": "a more cat like cat eating more ice cream",
        },
        {
            "sceneImage": "img/name_of_the_story_goes_here/scene2.png",
            "imagePrompt": "make an art masterpiece featuring cats eating ice cream, with unbelievable detail, cartoon, 3d",
            "description": "a more cat like cat eating more ice cream",
        }

}
```
do not return text or markdown, only json
"""

model="gpt-4-1106-preview"
#model="gpt-4-turbo-preview"
#model = "gpt-3.5-turbo-1106"

def create_assistant():
    assistant = client.beta.assistants.create(
      instructions=instructions,
      model=model,
      # TODO: consider using function calling to get more consistent json results, note this may be slower
      #tools=[{
      #    "type": "function",
      #    "function": make_prompts_function
      #}]
    )
    print(assistant)
    # write assistant id to file
    with open('assistant_id.txt', 'w') as f:
        f.write(assistant.id)

    return assistant


def get_assistant_id_from_file():
    # if file exists, read assistant id from file
    if not os.path.exists('assistant_id.txt'):
        create_assistant()
    with open('assistant_id.txt', 'r') as f:
        assistant_id = f.read()
    return assistant_id

def run_thread(assistant_id, thread_id):
    global client
    time.sleep(2)
    
    #runs = client.beta.threads.runs.list(
    #        thread_id=thread_id
    #)
    #print(runs)

    #print("creating run" )
    #print(f"for thread {thread_id}" )
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
    )

    print(run)
    #runs = client.beta.threads.runs.list(
    #        thread_id=thread_id
    #)
    #print(runs)

    
    print("retrieving:" )
    while (True):
        run = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id
        )
        print(f'loading, run status {run.status}')
        if run.status == 'failed':
            raise HTTPException(status_code=500, detail="Run is in failed state")
        if run.status == 'completed' or run.status == 'generating':
            break
        time.sleep(1)

    patchedClient = patch(client)
    response = patchedClient.beta.threads.messages.list(
        thread_id=thread_id,
        stream=True,
    )
    done = False
    for part in response:
        text = part.data[0].content[0].text.value
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
            done = True
        text = text.replace("\n","")
        text = text.replace("\t","")

        if text is not None and text != "":
            try:
                json_object = loads(text, OBJ | ARR)
                print(f"yielding: {json_object}")
                yield f"data: {json.dumps(json_object)}\n\n"
            except Exception as e:
                # throw error
                print(text)
                print(e)
                raise HTTPException(status_code=500, detail="Internal Error")
        if done:
            break
    print("done yielding")

def continue_thread(file_ids, assistant_id, thread_id, content):
    message = client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=content,
        file_ids=file_ids
    )

    #print(f"message_id {message.id}")
    return run_thread(assistant_id, thread_id)


def make_prompts(content):
    assistant_id = get_assistant_id_from_file()
    assistants = client.beta.assistants.list()
    assistant_exists = False

	# TODO maybe no .data? check this
    for asnt in assistants.data:
        if asnt.id == assistant_id:
            assistant_exists = True

    if not assistant_exists:
        assistant_id = create_assistant().id

    thread = client.beta.threads.create()
    print(thread)
    file_ids = []
    return continue_thread(file_ids, assistant_id, thread.id, content)


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
            #test_list = self._get_api_list(
            #    f"/threads/{thread_id}/messages",
            #    page=SyncCursorPage[ThreadMessage],
            #    options=make_request_options(
            #        extra_headers=extra_headers,
            #        extra_query=extra_query,
            #        extra_body=extra_body,
            #        timeout=timeout,
            #        query=maybe_transform(
            #            {
            #                "after": after,
            #                "before": before,
            #                "limit": limit,
            #                "order": order,
            #            },
            #            message_list_params.MessageListParams,
            #        ),
            #    ),
            #    model=ThreadMessage,
            #)
        else:
            # Call the original 'list' method for non-streaming requests
            return original_list(self, thread_id, after, before, limit, order, extra_headers, extra_query, extra_body, timeout)

    @wraps(original_list)
    async def async_list(self, thread_id: str, *args, stream: bool = False, **kwargs) -> Union[SyncCursorPage[ThreadMessage], Stream[MessageChunk]]:
        if stream:
            # TODO await?
            test = await self._get(
                f"/threads/{thread_id}/messages",
                stream=True,
                stream_cls=Stream[MessageChunk],
                # Add other necessary parameters and transformations similar to the completions call
            )
            return await original_list(self, thread_id, *args, **kwargs)
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

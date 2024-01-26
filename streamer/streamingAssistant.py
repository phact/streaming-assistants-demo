import json
import os
import time
from fastapi import HTTPException
from openai import OpenAI, AsyncOpenAI, Stream
from dotenv import load_dotenv
import re
from partial_json_parser import loads, Allow
from partial_json_parser.options import STR, OBJ, ARR
from streamer.streaming_assistant import patch


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


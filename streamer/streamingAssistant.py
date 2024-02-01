import json
import os
import time
from fastapi import HTTPException
from openai import OpenAI
from dotenv import load_dotenv
import re
from partial_json_parser import loads
from partial_json_parser.options import OBJ, ARR
from streaming_assistants import patch


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

model=os.getenv("model", "gpt-4-1106-preview")
print(f"using model: {model}")


# ensure the env vars for your model are set
client = patch(OpenAI())


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
You are a prompt generator that makes images iteratively MORE extreme.
The user will pass a prompt, you will come up with *a single json object* with an array of *3 to 5 scenes*. 

Each scene has a description and an image generation prompt (for dalee3).

For a prompt `a hungry cat` you might return the following json:

```json
{
    "gen_name_goes_here": [
        {
            "sceneImage": "img/gen_name/scene1.png",
            "imagePrompt": ""A hungry cat with expressive eyes, slightly open mouth, and whiskers pointing forwards, in anticipation of food. The cat has a sleek fur, perhaps a common domestic short-haired variety, with a mix of grey and white patches. The setting is a cozy kitchen, with a hint of a food bowl on the side, suggesting the cat's focus is on an approaching meal. The lighting is warm and welcoming, enhancing the cat's hopeful expression."",
            "description": "a hungry cat with it's mouth open",
        },
        {
            "sceneImage": "img/name_of_the_story_goes_here/scene2.png",
            "imagePrompt": "A very hungry cat with wide, pleading eyes and an eagerly open mouth, whiskers fully extended forward as if trying to catch a scent. The cat's fur is ruffled, emphasizing its desperation, with pronounced grey and white patches, indicating a domestic short-haired breed. The background is a simple kitchen scene, with a food bowl prominently empty to the side, underscoring the cat's urgent need for food. The lighting is soft, casting gentle shadows that highlight the cat's intense gaze and anxious posture.",
            "description": "a hungrier cat",
        },
        {
            "sceneImage": "img/name_of_the_story_goes_here/scene3.png",
            "imagePrompt": "An extremely hungry cat, its eyes wide and frantic, mouth wide open in an urgent meow. The cat's fur appears disheveled, enhancing its desperate state, with distinct grey and white patches typical of a domestic short-haired breed. It's sitting in a sparse kitchen, focusing intently on an empty food bowl, symbolizing its acute hunger. The lighting casts dramatic shadows, accentuating the cat's fervent expression and the stark emptiness of the bowl, creating a poignant scene of anticipation.",
            "description": "an extremely hungry cat",
        },
        {
            "sceneImage": "img/name_of_the_story_goes_here/scene4.png",
            "imagePrompt": "A cat in the throes of extreme hunger, its eyes nearly bulging with desperation, mouth agape in a silent plea. The fur is wildly unkempt, standing on end to depict the severity of its condition, showcasing a stark contrast of grey and white. The setting is a barren kitchen, with the cat's intense gaze fixed on a glaringly empty, scratched food bowl, amplifying the sense of urgency. Dramatic, high-contrast lighting throws deep shadows, further dramatizing the cat's dire situation and its desperate anticipation for food.",
            "description": "an insanely hungry cat",
        },
        {
            "sceneImage": "img/name_of_the_story_goes_here/scene5.png",
            "imagePrompt": "A cat embodying the pinnacle of hunger, with gaunt features and eyes dilated in sheer desperation. Its mouth is agape in a silent, haunting scream for food, showcasing the extreme urgency of its need. The fur is more than unkempt; it's patchy and coarse, signifying long-term neglect and starvation, with a color palette dominated by stark greys and whites. The setting is a desolate kitchen, with the cat perched beside an utterly empty, dust-covered food bowl, symbolizing the prolonged absence of sustenance. A single, stark light source casts severe, elongated shadows, amplifying the grim atmosphere and the cat's desperate condition.",
            "description": "a cat embodying the pinnacle of hunger"
        },
        ...

}
```
do not return text or markdown, only json
"""



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
    print(f"assistant created, id:{assistant.id}")
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

    print(f"run created: id:{run.id}")
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
        print(text)

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


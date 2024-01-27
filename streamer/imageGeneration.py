import os
from io import BytesIO
import openai                  # for handling error types
import base64                  # for decoding images if recieved in the reply
from PIL import Image          # pillow, for processing image types

from openai import OpenAI
client = OpenAI()  # will use environment variable "OPENAI_API_KEY"

def create_directory(path):
    try:
        # The exist_ok=True parameter will not raise an error if the directory already exists
        os.makedirs(path, exist_ok=True)
        print(f"Directory '{path}' created successfully.")
    except Exception as e:
        print(f"Error creating directory '{path}': {e}")

def make_image(gen_name, scene_index, prompt):
    directory = f"streamer/static/img/{gen_name}"
    create_directory(directory)
    path = f"{directory}/scene{scene_index}.png"
    url = f"/img/{gen_name}/scene{scene_index}.png"
    response_format = "b64_json"

    image_params = {
     "model": "dall-e-3",
     "size": "1024x1024",
     "prompt": prompt,
     "quality": "standard", # "hd"
     "response_format" : response_format
    }

    try:
        images_response = client.images.generate(**image_params)
    except openai.APIConnectionError as e:
        print("Server connection error: {e.__cause__}")  # from httpx.
        raise
    except openai.RateLimitError as e:
        print(f"OpenAI RATE LIMIT error {e.status_code}: (e.response)")
        raise
    except openai.APIStatusError as e:
        print(f"OpenAI STATUS error {e.status_code}: (e.response) \n Message {e.message} \n Prompt {prompt}")
        raise
    except openai.BadRequestError as e:
        print(f"OpenAI BAD REQUEST error {e.status_code}: (e.response)")
        raise
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise

    # get the prompt used if rewritten by dall-e-3, null if unchanged by AI
    revised_prompt = images_response.data[0].revised_prompt

    image_url_list = []
    image_data_list = []
    for image in images_response.data:
        image_url_list.append(image.model_dump()["url"])
        image_data_list.append(image.model_dump()["b64_json"])

    image = Image.open(BytesIO(base64.b64decode(image_data_list[0])))
    image.save(f"{path}")
    print(f"{path} was saved")


    return {"success": True, "url": url, "revised_prompt": revised_prompt}

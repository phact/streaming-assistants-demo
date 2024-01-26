import time

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import json
import random

from starlette.responses import StreamingResponse

from streamer.streamingAssistant import make_prompts
from streamer.imageGeneration import make_image

app = FastAPI()

def event_stream():
    while True:
        yield f"data: The server time is {time.ctime()}\n\n"
        time.sleep(1)

@app.get("/events")
def events():
    return StreamingResponse(event_stream(), media_type="text/event-stream")
@app.get("/generate_prompts")
def generate_prompts(
        content: str = Query(None, description="The content for the story")
    ) -> StreamingResponse:
    if content is None:
        raise HTTPException(status_code=400, detail="Content parameter is required")

    try:
        return StreamingResponse(make_prompts(content), media_type="text/event-stream")
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/save")
def save(
        content: str = Query(None, description="The content for the story")
):
    if content is None:
        raise HTTPException(status_code=400, detail="Content parameter is required")

    with open('streamer/static/storylines.json', 'r') as f:
        stories = json.load(f)
        contentObject = json.loads(content)
        storyName = list(contentObject.keys())[0]
        stories[storyName] = contentObject[storyName]
    with open('streamer/static/storylines.json', 'w') as f:
        json.dump(stories, f, indent=4)
    return {"success": True}

@app.get("/generate_image")
def image(
        gen_name: str = Query(None, description="name"),
        scene_index: str = Query(None, description="Scene index"),
        prompt: str = Query(None, description="Image prompt")
):
    if prompt is None or gen_name is None or scene_index is None:
        raise HTTPException(status_code=400, detail="required params -- prompt, gen_name, scene_index")

    image_url = make_image(gen_name, scene_index, prompt)
    return image_url
    #url = f"/img/{gen_name}/scene{scene_index}.png"
    #return {"success": True, "url": url, "revised_prompt": "tweaked " +prompt}

# Serve Static Files
app.mount("/", StaticFiles(directory="./streamer/static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)


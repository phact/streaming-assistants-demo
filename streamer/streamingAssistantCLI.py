from streamer.streamingAssistant import make_prompts

if __name__ == "__main__":
    response = make_prompts("I like puppies")
    for data in response:
        print(data[6:])
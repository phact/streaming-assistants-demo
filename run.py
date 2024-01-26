# run.py
import uvicorn

def main():
    uvicorn.run("streamer.main:app", host="0.0.0.0", port=8001, workers=8, reload=True)

if __name__ == "__main__":
    main()


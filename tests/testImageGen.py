import os

from dotenv import load_dotenv
load_dotenv("./.env")

from streamer.imageGeneration import make_image




prompt = "A puppy in a wonderland of sweets and treats. Its sparkling blue eyes are wide with joy as it hops around, its snow-white fur providing stark contrast to the colorful candy realm. The puppy wears a tiny hat made of golden syrup and sprinkles, its status amid the confectionery landscape unquestioned. Surrounding it are gingerbread houses, rivers of chocolate, and fields of candied fruits under a sky made of cotton candy. The scene is lit by a multitude of shimmering fairy lights, making every detail pop with an enchanting glow."
make_image("test", 1, prompt)

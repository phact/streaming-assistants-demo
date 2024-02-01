let generated_data = {}
let gen_name = ""
let imageRequested = []

async function streamSSE(url) {
    const response = await fetch(url, { headers: { Accept: 'text/event-stream' } });

    // The ReadableStream interface of the Streams API represents a readable stream of byte data.
    const reader = response.body.getReader();
    let decoder = new TextDecoder();

    while (true) {
        const { done, value } = await reader.read();

        // When the stream is complete, break the loop
        if (done) break;

        // Decode and process the chunk of data
        const chunk = decoder.decode(value, { stream: true });
        processChunk(chunk);
    }
}

function processChunk(chunk) {
    // Process each line of the chunk
    chunk.split('\n\n').forEach(line => {
        if (line.startsWith('data:')) {
            const data = line.replace('data: ', '');
            console.log('Data:', data);
            displayIterations(JSON.parse(data))
        }
    });
}

document.getElementById('createForm').addEventListener('submit', function(e) {
    e.preventDefault();
    const statusText = document.getElementById('status');
    statusText.value = "loading"
    statusText.style.display = "block"
    const content = document.getElementById('contentInput').value;
    streamSSE(`/generate_prompts?content=${content}`);
});

function displayIterations(response_data) {
    const statusText = document.getElementById('status');
    statusText.value = "loading"
    statusText.style.display = "none"
    const container = document.getElementById('container');

    name = Object.keys(response_data)[0]
    if (generated_data === {} || name != gen_name){
        container.innerHTML = ''; // Clear previous content
    }
    generated_data = response_data
    gen_name = name

    Object.keys(response_data).forEach((name) => {
        let scenes = response_data[name]
        scenes.forEach((scene, index) => {
            var append = false;
            let sceneElement = document.getElementById(`scene${index}`)
            if (sceneElement === null){
                append = true;
                sceneElement = document.createElement('div')
                sceneElement.id = `scene${index}`
            }
            if (imageRequested.size < index) {
                imageRequested.push(false)
            }

            let imagePromptElement = document.getElementById(`imagePrompt${index}`)
            if (imagePromptElement !== null && scene?.imagePrompt != undefined){
                if (!imageRequested[index]){
                    imageRequested[index] = true
                    imagePromptElement.value = scene?.imagePrompt
                    generateImage(scene?.imagePrompt, encodeURI(gen_name), index)
                }else{
                    if (generated_data[name][index].imagePrompt != scene?.imagePrompt){
                        imagePromptElement.value = scene?.imagePrompt
                        generateImage(scene?.imagePrompt, encodeURI(gen_name), index)
                    }
                }
            }

            let sceneImage = document.getElementById(`sceneImage${index}`)
            let sceneImageSrc = ""
            let sceneImageAlt = ""
            if (sceneImage?.src != null && sceneImage?.src.startsWith('http')) {
                sceneImageSrc = sceneImage.src
                sceneImageAlt = sceneImage.alt
            }
            let proposedInner = `
                    <h3>Iteration ${index + 1}</h3>
                    <h4>Description</h4>
                    <span id="sceneDescription${index}" class="scene-description">${scene?.description}</span>
                    <h4>Prompt</h4>
                    <span id="imagePrompt${index}" class="image-prompt">${scene?.imagePrompt}</span>
                    <img class="sceneImage" id="sceneImage${index}" src="${sceneImageSrc}" alt="${sceneImageAlt}">
                    <button onclick="generateImage('${encodeURI(scene?.imagePrompt)}', '${encodeURI(name)}',${index})">
                      Re-generate Image
                    </button>
            `;
            if (sceneElement.innerHTML !== proposedInner) {
                sceneElement.innerHTML = proposedInner
                if (append) {
                    container.appendChild(sceneElement);
                }
            }
        })
    });
}

function generateImage(imagePrompt, name, sceneIndex) {
    if (imagePrompt == null){
        imagePrompt = document.getElementById("imagePrompt"+sceneIndex)?.value
    }
    fetch(`/generate_image?prompt=${imagePrompt}&gen_name=${name}&scene_index=${sceneIndex}`)
        .then(response => response.json())
        .then(jsonResponse=> {
            if (jsonResponse.success){
				url = jsonResponse.url
				imagePrompt = jsonResponse.revised_prompt
                image = document.getElementById(`sceneImage${sceneIndex}`)
				image.src = url;
                image.alt = imagePrompt;
				generated_data[gen_name][sceneIndex].sceneImage = url;
				document.getElementById(`imagePrompt${sceneIndex}`).value = imagePrompt;
            }
        });
}
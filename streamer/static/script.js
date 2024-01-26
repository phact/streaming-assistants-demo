let generated_data = {}
let gen_name = ""

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
            displayIterationsForEditing(JSON.parse(data))
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

function displayIterationsForEditing(response_data) {
    const statusText = document.getElementById('status');
    const saveButton = document.getElementById('saveButton');
    statusText.value = "loading"
    statusText.style.display = "none"
    //saveButton.style.display = "block"
    const container = document.getElementById('container');
    if (generated_data === {}){
        container.innerHTML = ''; // Clear previous content
    }
    generated_data = response_data

    Object.keys(response_data).forEach((name) => {
        gen_name = name
        scenes = response_data[name]
        scenes.forEach((scene, index) => {
            var append = false;
            let sceneElement = document.getElementById(`scene${index}`)
            if (sceneElement === null){
                append = true;
                sceneElement = document.createElement('div')
                sceneElement.id = `scene${index}`
            }
            imagePromptElement = document.getElementById(`imagePrompt${index}`)
            if (imagePromptElement != null){
                if (scene.imagePrompt != undefined) {
                    currentPrompt = imagePromptElement.value;
                    if (currentPrompt === 'undefined') {
                        imagePromptElement.value = scene?.imagePrompt
                        generateImage(scene?.imagePrompt, encodeURI(gen_name), index)
                    }
                    else{
                        console.log("currentPrompt:"+currentPrompt)
                    }
                }
            }
            sceneImage = document.getElementById(`sceneImage${index}`)
            sceneImageSrc = ""
            sceneImageAlt = ""
            // TODO: do this for other editable elements
            if (sceneImage?.src != null && sceneImage?.src.startsWith('http')) {
                console.log("this image has already been generated, not changing src or alt")
                sceneImageSrc = sceneImage.src
                sceneImageAlt = sceneImage.alt
                generated_data[name][index].sceneImage = sceneImageSrc
                generated_data[name][index].imagePrompt = sceneImageAlt
            }
            proposedInner = `
                    <h3>itteration ${index + 1}</h3>
                    <textarea id="sceneDescription${index}" class="scene-description">${scene?.description}</textarea>
                    <textarea id="imagePrompt${index}" class="image-prompt">${scene?.imagePrompt}</textarea>
                    <button onclick="generateImage(null, '${encodeURI(name)}', ${index})">Re-generate Image</button>
                    <img class="sceneImage" id="sceneImage${index}" src="${sceneImageSrc}" alt="${sceneImageAlt}">
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
				generated_data[gen_name][sceneIndex].imagePrompt = imagePrompt;
				generated_data[gen_name][sceneIndex].description = document.getElementById(`sceneDescription${sceneIndex}`);
            }
        });
}


function save() {
	const statusText = document.getElementById('status');
	statusText.value = "saving"
	statusText.style.display = "block"
    fetch(`/save?content=${JSON.stringify(generated_data)}`)
        .then(response => response.json())
        .then(jsonResponse=> {
            if (jsonResponse.success){
				const statusText = document.getElementById('status');
				statusText.value = "saved"
				statusText.style.display = "block"
            } else{
				const statusText = document.getElementById('status');
				statusText.value = "could not save"
				statusText.style.display = "block"
            }
        });
}


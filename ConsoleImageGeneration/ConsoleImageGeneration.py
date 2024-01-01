import os
import openai
import webbrowser

def get_env_var(name):
    env_var = os.getenv(name)
    if not env_var:
        raise Exception('No {} environment variable'.format(name))
    return env_var

print('Getting environment variables')
api_key = get_env_var("OPENAI_API_KEY")
organization = get_env_var("OPENAI_ORG")
openai.organization = organization
openai.api_key = api_key

def call_openai(prompt, size):
    if size == "s" or size == "S":
        sizeValue = "256x256"
    elif size == "m" or size == "M":
        sizeValue = "512x512"
    elif size == "l" or size == "L":
        sizeValue = "1024x1024"
    response = openai.images.generate(
        model = "dall-e-3",
        prompt = prompt,
        size = sizeValue
    )
    return response

def open_url(datum):
    url = datum["url"]
    webbrowser.open_new_tab(url)

prompt = input("Prompt: ")
size = input("Size (S,M,L): ")
print("Calling OpanAI")
response = call_openai(prompt, size)

url = response.data[0].url
print(url)
input("Press ENTER to open URL")
webbrowser.open_new_tab(url)
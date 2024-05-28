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
    if size == "1":
        sizeValue = "1024x1024"
    elif size == "2":
        sizeValue = "1024x1792"
    elif size == "3":
        sizeValue = "1792x1024"
    response = openai.images.generate(
        model = "dall-e-3",
        prompt = prompt,
        quality = 'hd',
        size = sizeValue
    )
    return response

prompt = input("Prompt: ")
print('Choose size:')
print('1: 1024x1024')
print('2: 1024x1792 (portrait)')
print('3: 1792x1024 (landscape)')
size = input("Size (1,2,3): ")
print("Calling OpanAI")
response = call_openai(prompt, size)

url = response.data[0].url
revised_prompt = response.data[0].revised_prompt
print(url)
print(revised_prompt)
input("Press ENTER to open URL")
webbrowser.open_new_tab(url)
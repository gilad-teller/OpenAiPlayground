import os
import openai

def get_env_var(name):
    env_var = os.getenv(name)
    if not env_var:
        raise Exception('No {} environment variable'.format(name))
    return env_var

def call_openai(messages):
    i = 0
    while True:
        i += 1
        try:
            response = openai.chat.completions.create(
              model="gpt-4o",
              messages = messages,
              stream=True
            )
            return response
        except Exception as e:
            if i < 3:
                print('Error, trying again')
            else:
                raise e

RED = "\033[1;31m"
GREEN = "\033[0;32m"
BLUE = "\033[0;34m"
RESET = "\033[0;0m"

print('Getting environment variables')
api_key = get_env_var("OPENAI_API_KEY")
organization = get_env_var("OPENAI_ORG")
openai.organization = organization
openai.api_key = api_key

userInput = input(f"\n{BLUE}System:{RESET} ") or "You are a helpful assistant."
messages = [
    {"role": "system", "content": userInput},
]
print('You can now start chatting')
userInput = input(f"\n{RED}User:{RESET} ")
while userInput:
    messages.append({"role": "user", "content": userInput})
    response = call_openai(messages)
    print(f"\n{GREEN}ChatGPT:{RESET} ", end ='')
    chatResponse = ''
    for chunk in response:
        if chunk.choices[0].delta.content is not None:
            print(chunk.choices[0].delta.content, end="")
            chatResponse += chunk.choices[0].delta.content
    messages.append({ 'role': 'assistant', 'content': chatResponse })
    userInput = input(f"\n\n{RED}User:{RESET} ")
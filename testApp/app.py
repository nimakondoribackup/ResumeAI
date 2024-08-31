from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)

# Set up the OpenAI API key
key = "PUT IN API KEY HERE"

@app.route("/chatgpt", methods=["GET"])
def chatgpt():

    client = OpenAI(api_key=key)

    response = client.chat.completions.with_raw_response.create(
    messages=[{
        "role": "user",
        "content": "Say this is a test",
    }],
    model="gpt-3.5-turbo",
    )
    print(response.headers.get('x-request-id'))

    # get the object that `chat.completions.create()` would have returned
    completion = response.parse()
    return completion

if __name__ == "__main__":
    app.run(debug=True)
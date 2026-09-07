from flask import Flask, request, jsonify, abort
import os
import threading
import asyncio
import json
import requests
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError

# Interactions endpoint that defers and posts followup with agent result.
# Requires environment variables in Vercel:
# - DISCORD_PUBLIC_KEY (hex)
# - APPLICATION_ID (string)
# - NVIDIA_API_KEY (for run_agent)
# Note: This handler only sends text responses; file attachments are not uploaded in followups.

app = Flask(__name__)

DISCORD_PUBLIC_KEY = os.environ.get("DISCORD_PUBLIC_KEY")
APPLICATION_ID = os.environ.get("APPLICATION_ID")
if not DISCORD_PUBLIC_KEY:
    print("WARNING: DISCORD_PUBLIC_KEY not set. Set it in Vercel environment variables.")
if not APPLICATION_ID:
    print("WARNING: APPLICATION_ID not set. Set it in Vercel environment variables.")

from agent import run_agent


def verify_discord_request(req):
    signature = req.headers.get('X-Signature-Ed25519')
    timestamp = req.headers.get('X-Signature-Timestamp')
    if not signature or not timestamp:
        return False
    body = req.get_data().decode('utf-8')
    try:
        verify_key = VerifyKey(bytes.fromhex(DISCORD_PUBLIC_KEY))
        verify_key.verify((timestamp + body).encode(), bytes.fromhex(signature))
        return True
    except Exception:
        return False


def post_followup(interaction_token, content):
    # POST to followup webhook for this interaction
    url = f"https://discord.com/api/v10/webhooks/{APPLICATION_ID}/{interaction_token}"
    headers = {"Content-Type": "application/json"}
    payload = {"content": content}
    try:
        requests.post(url, headers=headers, json=payload, timeout=15)
    except Exception as e:
        print(f"Failed to post followup: {e}")


def handle_command_async(interaction):
    try:
        name = interaction.get('data', {}).get('name')
        options = interaction.get('data', {}).get('options', [])
        # Map command to prompt
        if name == 'ask':
            prompt = next((o['value'] for o in options if o['name'] == 'question'), '')
        elif name in ('image', 'gif'):
            prompt = next((o['value'] for o in options if o['name'] == 'prompt'), '')
        elif name == 'build':
            prompt = next((o['value'] for o in options if o['name'] == 'description'), '')
        else:
            prompt = f"Command: {name}"

        # Run the agent (no history for interactions)
        result = asyncio.run(run_agent([], prompt))
        text = result.text or '(no text response)'
        # If the agent produced attachments, append a note
        if result.image_bytes:
            text += '\n\n(Generated an image; attachments are not uploaded via this endpoint.)'
        if result.gif_bytes:
            text += '\n\n(Generated a GIF; attachments are not uploaded via this endpoint.)'
        if result.zip_path:
            text += f"\n\n(Generated files packaged at {result.zip_path}; download not attached.)"

        post_followup(interaction['token'], text)
    except Exception as e:
        print(f"Error handling command: {e}")
        try:
            post_followup(interaction['token'], f"Error: {e}")
        except Exception:
            pass


@app.route('/api/interactions', methods=['POST'])
def interactions_endpoint():
    if not verify_discord_request(request):
        abort(401)
    data = request.json
    if data.get('type') == 1:
        return jsonify({'type': 1})
    if data.get('type') == 2:
        # Defer the interaction and run the command asynchronously
        interaction = data
        t = threading.Thread(target=handle_command_async, args=(interaction,))
        t.start()
        # 5 = DEFERRED
        return jsonify({'type': 5})
    return jsonify({'type': 4, 'data': {'content': 'Unsupported interaction type.'}})


@app.route('/api/healthz', methods=['GET'])
def healthz():
    return 'ok', 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 3000)))

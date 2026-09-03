from flask import Flask, request, jsonify, abort
import os
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError

# Simple Discord interactions handler suitable for Vercel serverless (api/interactions.py)
# Environment variables required in Vercel project settings:
# - DISCORD_PUBLIC_KEY : application public key (hex)
# Note: This handler only verifies and responds to interactions (slash commands).

app = Flask(__name__)

DISCORD_PUBLIC_KEY = os.environ.get("DISCORD_PUBLIC_KEY")
if not DISCORD_PUBLIC_KEY:
    # Log at startup in serverless logs; verification will fail without this
    print("WARNING: DISCORD_PUBLIC_KEY not set. Set it in your Vercel Environment Variables.")

@app.route('/api/interactions', methods=['POST'])
def interactions_endpoint():
    signature = request.headers.get('X-Signature-Ed25519')
    timestamp = request.headers.get('X-Signature-Timestamp')
    if not signature or not timestamp:
        abort(401)

    body = request.get_data().decode('utf-8')

    try:
        verify_key = VerifyKey(bytes.fromhex(DISCORD_PUBLIC_KEY))
        verify_key.verify((timestamp + body).encode(), bytes.fromhex(signature))
    except (BadSignatureError, Exception) as e:
        # Signature invalid
        abort(401)

    data = request.json

    # PING (type=1) must be replied to with a PONG per Discord
    if data.get('type') == 1:
        return jsonify({'type': 1})

    # Example: simple response for any command (type 2 = application command)
    # Replace with routing logic to handle different commands
    if data.get('type') == 2:
        # Echo the command name back
        name = data.get('data', {}).get('name', 'command')
        return jsonify({
            'type': 4,
            'data': {
                'content': f'Received slash command: {name} (handled by Vercel interactions endpoint)'
            }
        })

    # Fallback: acknowledge
    return jsonify({'type': 5})

# Health check for manual testing
@app.route('/api/healthz', methods=['GET'])
def healthz():
    return 'ok', 200

# When running locally for testing: flask run --port=3000
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 3000)))

import os
import json
from flask import Flask, request, jsonify
import requests
from openai import OpenAI
from dotenv import load_dotenv # For loading .env file

# Load environment variables from .env file
# load_dotenv()

app = Flask(__name__)

# --- Configuration ---
WEBHOOK_VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN")
GRAPH_API_TOKEN = os.getenv("GRAPH_API_TOKEN")
PORT = os.getenv("PORT", 5002) # Default to 5002 if not set
OPEN_AI_API_KEY = os.getenv("OPEN_AI_API_KEY")

# --- Initialize OpenAI Client ---
if not OPEN_AI_API_KEY:
    print("Error: OpenAI API key (OPEN_AI_API_KEY) is not set in environment variables.")
    # You might want to exit or handle this more gracefully
    # exit()

try:
    client = OpenAI(api_key=OPEN_AI_API_KEY)
except Exception as e:
    print(f"Error initializing OpenAI client: {e}")
    client = None # Set client to None if initialization fails


# --- OpenAI Chat Completion Function ---
def get_chat_completion(user_message):
    if not client:
        print("OpenAI client not initialized. Cannot fetch completion.")
        return "Maaf sedang ada kendala pada Asisten AI kami. Mohon ditunggu hingga kami menghubungi Anda kembali..."
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": user_message}
            ]
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"Error fetching completion from OpenAI: {e}")
        # Return a generic error message to the user
        return "Ada kesalahan dalam memproses permintaan Anda. Mohon coba lagi nanti."

# --- Webhook POST Endpoint (for receiving messages) ---
@app.route("/webhook", methods=["POST"])
def webhook_post():
    # Log incoming messages
    data = request.get_json()
    print(f"Incoming webhook message: {json.dumps(data, indent=2)}")

    # Check if the webhook request contains a message
    # (Structure based on WhatsApp Cloud API payload)
    try:
        changes = data.get("entry", [{}])[0].get("changes", [{}])[0]
        value = changes.get("value", {})
        message_object = value.get("messages", [{}])[0]
        metadata = value.get("metadata", {})
    except (IndexError, AttributeError, TypeError) as e:
        print(f"Error parsing webhook payload structure: {e}")
        return jsonify({"status": "error", "message": "Malformed payload"}), 400


    if message_object and message_object.get("type") == "text":
        business_phone_number_id = metadata.get("phone_number_id")
        user_message_text = message_object.get("text", {}).get("body")
        message_from = message_object.get("from")
        message_id = message_object.get("id")

        if not all([business_phone_number_id, user_message_text, message_from, message_id]):
            print("Error: Missing essential message data.")
            return jsonify({"status": "error", "message": "Missing message data"}), 400

        print(f"User message: '{user_message_text}' from {message_from}")

        # Get AI reply
        ai_reply = get_chat_completion(user_message_text)
        print(f"AI reply: {ai_reply}")

        # Send reply message via Facebook Graph API
        graph_api_url = f"https://graph.facebook.com/v22.0/{business_phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {GRAPH_API_TOKEN}",
            "Content-Type": "application/json",
        }
        payload_reply = {
            "messaging_product": "whatsapp",
            "to": message_from,
            "text": {"body": ai_reply},
            "context": {"message_id": message_id},
        }
        try:
            response_reply = requests.post(graph_api_url, headers=headers, json=payload_reply)
            response_reply.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
            print(f"Reply sent successfully: {response_reply.json()}")
        except requests.exceptions.RequestException as e:
            print(f"Error sending reply message: {e}")
            if e.response is not None:
                print(f"Response content: {e.response.content}")
            # Optionally, you might want to retry or log more details

        # Mark incoming message as read
        payload_read = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        try:
            response_read = requests.post(graph_api_url, headers=headers, json=payload_read)
            response_read.raise_for_status()
            print(f"Message marked as read: {response_read.json()}")
        except requests.exceptions.RequestException as e:
            print(f"Error marking message as read: {e}")
            if e.response is not None:
                print(f"Response content: {e.response.content}")

    return jsonify({"status": "success"}), 200


# --- Webhook GET Endpoint (for verification) ---
@app.route("/webhook", methods=["GET"])
def webhook_get():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    print(f"GET /webhook - Mode: {mode}, Token: {token}, Challenge: {challenge}")

    if mode and token:
        if mode == "subscribe" and token == WEBHOOK_VERIFY_TOKEN:
            print("Webhook verified successfully!")
            return challenge, 200
        else:
            print("Webhook verification failed: Mode or token mismatch.")
            return jsonify({"status": "error", "message": "Verification token mismatch"}), 403
    else:
        print("Webhook verification failed: Missing mode or token.")
        return jsonify({"status": "error", "message": "Missing mode or token"}), 400


# --- Root GET Endpoint ---
@app.route("/", methods=["GET"])
def index():
    return """
    <pre>Nothing to see here.
    Python WhatsApp Webhook is running.
    Checkout README.md to start.</pre>
    """, 200


if __name__ == "__main__":
    if not all([WEBHOOK_VERIFY_TOKEN, GRAPH_API_TOKEN, OPEN_AI_API_KEY]):
        print("CRITICAL ERROR: One or more required environment variables are not set.")
        print("Please check WEBHOOK_VERIFY_TOKEN, GRAPH_API_TOKEN, OPEN_AI_API_KEY.")
    else:
        print(f"Starting Flask server on port {PORT}...")
        # Set debug=False for production
        # Use a production WSGI server like Gunicorn or Waitress for production
        app.run(host="0.0.0.0", port=int(PORT), debug=True)

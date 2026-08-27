import os
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_number = os.getenv("TWILIO_PHONE_NUMBER")
customer_number = os.getenv("MY_PHONE_NUMBER")

client = Client(account_sid, auth_token)

print("TO:", customer_number)
print("FROM:", twilio_number)

call = client.calls.create(
    to=customer_number,
    from_=twilio_number,
    url="https://effects-galvanize-defensive.ngrok-free.dev/voice"
)

print("Call started!")
print("Call SID:", call.sid)
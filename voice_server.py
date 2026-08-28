from fastapi import FastAPI, Request
from fastapi.responses import Response
from langchain_openai import ChatOpenAI
import json
from twilio.rest import Client
from dotenv import load_dotenv
from prompt import SYSTEM_PROMPT
import os
from datetime import datetime, timedelta
import threading
import time
from fastapi import Query

customers = {}

app = FastAPI()

model = ChatOpenAI(model="gpt-4o-mini")

load_dotenv()

twilio_client = Client(
    os.getenv("TWILIO_ACCOUNT_SID"),
    os.getenv("TWILIO_AUTH_TOKEN")
)

whatsapp_number = os.getenv("TWILIO_WHATSAPP_NUMBER")



@app.post("/callback_voice")
async def callback_voice(request: Request):

    original_call_sid = request.query_params.get("original_call_sid")

    print("CALLBACK STARTED")

    if not original_call_sid:
        return Response(
            content="""
            <Response>
                <Say>
                    Sorry, we could not find your previous conversation.
                </Say>
                <Hangup/>
            </Response>
            """,
            media_type="application/xml"
        )

    if original_call_sid not in customers:

        return Response(
            content="""
            <Response>
                <Say>
                    Sorry, we could not find your previous conversation.
                </Say>
                <Hangup/>
            </Response>
            """,
            media_type="application/xml"
        )

    customer = customers[original_call_sid]

    website_type = customer.get("website_type") or "website"

    twiml = f"""
    <Response>

        <Say>
            Hi! This is the website consultant calling you back as requested.
            We were discussing your {website_type}.
            Are you available to continue our conversation?
        </Say>

        <Gather
            input="speech"
            action="https://effects-galvanize-defensive.ngrok-free.dev/process_callback_speech?original_call_sid={original_call_sid}"
            method="POST"
            speechTimeout="5"
            speechModel="deepgram_nova-3"
            language="multi">
        </Gather>

    </Response>
    """

    return Response(
        content=twiml,
        media_type="application/xml"
    )

@app.post("/voice")
async def voice():
    twiml = """
    <Response>
        <Say>Hello are you looking for a website?</Say>
        <Gather input="speech" action="https://effects-galvanize-defensive.ngrok-free.dev/process_speech"  method="POST" speechTimeout="3" speechModel="deepgram_nova-3" language="multi"></Gather>
    </Response>
    """

    return Response(content=twiml, media_type="application/xml")

def get_ai_response(speech, customer):
    prompt = f'''
        {SYSTEM_PROMPT}
        CURRENT CUSTOMER INFORMATION:
        {json.dumps(customer, ensure_ascii=False, indent=2)}
        CUSTOMER'S NEW MESSAGE:
        {speech}
    '''

    response = model.invoke(prompt)

    return response.content


def calculate_lead_score(customer):

    score = 0

    if customer.get("website_type"):
        score += 2

    if customer.get("budget"):
        score += 2

    if customer.get("timeline"):
        score += 2

    if customer.get("features"):
        score += 1

    if customer.get("intent") == "high":
        score += 3

    elif customer.get("intent") == "medium":
        score += 1

    return score

def classify_lead(score):

    if score >= 7:
        return "HOT"

    elif score >= 3:
        return "WARM"

    else:
        return "COLD"
    

def send_hot_lead_whatsapp(customer):

    customer_phone = customer.get("customer_phone")
    content_sid = os.getenv("WHATSAPP_CONTENT_SID")

    print("WHATSAPP DEBUG")
    print("Customer phone:", customer_phone)
    print("WhatsApp sender:", whatsapp_number)

    if not customer_phone:
        print("ERROR: CUSTOMER PHONE IS EMPTY")
        return False

    if not whatsapp_number:
        print("ERROR: WHATSAPP NUMBER IS EMPTY")
        return False

    if not content_sid:
        print("ERROR: WHATSAPP_CONTENT_SID IS EMPTY")
        return False

    if not customer_phone.startswith("whatsapp:"):
        customer_phone = f"whatsapp:{customer_phone}"

    website_type = customer.get("website_type") or "website"

    content_variables = json.dumps({
        "1": website_type
    })

    try:

        whatsapp_message = twilio_client.messages.create(
            from_=whatsapp_number,
            to=customer_phone,
            content_sid=content_sid,
            content_variables=content_variables
        )

        print("WHATSAPP MESSAGE CREATED")
        print("Message SID:", whatsapp_message.sid)
        print("Status:", whatsapp_message.status)

        return True

    except Exception as e:

        print("WHATSAPP ERROR:")
        print(e)

        return False


def customer_is_busy(speech):

    if not speech:
        return False

    speech_lower = speech.lower()

    busy_phrases = [
        "i am busy",
        "i'm busy",
        "im busy",
        "busy right now",
        "i am working",
        "i'm working",
        "not free",
        "not available",
        "can't talk",
        "cannot talk",
        "call me tomorrow",
        "talk tomorrow",
        "later",
        "call later",
        "talk later",
        "abhi busy",
        "abhi kaam mein hoon",
        "baad mein baat",
        "kal call karna",
        "kal baat karna",
    ]

    return any(
        phrase in speech_lower
        for phrase in busy_phrases
    )


@app.post("/process_callback_speech")
async def process_callback_speech(request: Request):

    form_data = await request.form()

    speech = form_data.get("SpeechResult")

    original_call_sid = request.query_params.get(
        "original_call_sid"
    )

    print(" CALLBACK CUSTOMER SAID:", speech)
    print("Original Call SID:", original_call_sid)

    if not original_call_sid or original_call_sid not in customers:

        return Response(
            content="""
            <Response>
                <Say>
                    Sorry, we could not find your previous conversation.
                </Say>
                <Hangup/>
            </Response>
            """,
            media_type="application/xml"
        )

    customer = customers[original_call_sid]

    ai_response = get_ai_response(
        speech,
        customer
    )

    try:
        data = json.loads(ai_response)

    except json.JSONDecodeError:

        data = {
            "response": "Sorry, could you please repeat that?",
            "end_call": False,
            "updated_info": {}
        }

    response_text = data.get(
        "response",
        "Could you please tell me more?"
    )

    end_call = data.get(
        "end_call",
        False
    )

    updated_info = data.get(
        "updated_info",
        {}
    )

    # Update customer memory
    for key, value in updated_info.items():

        if key not in customer:
            continue

        if value is None:
            continue

        if key == "features":

            if isinstance(value, list):

                for feature in value:

                    if feature not in customer["features"]:
                        customer["features"].append(feature)

        else:

            customer[key] = value

    print("\nCALLBACK CUSTOMER MEMORY:")

    print(
        json.dumps(
            customer,
            ensure_ascii=False,
            indent=4
        )
    )

    if end_call:

        twiml = f"""
        <Response>

            <Say>
                {response_text}
            </Say>

            <Hangup/>

        </Response>
        """

    else:

        twiml = f"""
        <Response>

            <Say>
                {response_text}
            </Say>

            <Gather
                input="speech"
                action="https://effects-galvanize-defensive.ngrok-free.dev/process_callback_speech?original_call_sid={original_call_sid}"
                method="POST"
                speechTimeout="5"
                speechModel="deepgram_nova-3"
                language="multi">
            </Gather>

        </Response>
        """

    return Response(
        content=twiml,
        media_type="application/xml"
    )


def schedule_callback_next_day(original_call_sid, customer_phone):

    def make_callback():

        print(" CALLBACK SCHEDULED")
        print("Customer:", customer_phone)
        print("Original Call SID:", original_call_sid)
        print("Callback: TOMORROW")

        time.sleep(24 * 60 * 60)

        try:

            callback_url = (
                "https://effects-galvanize-defensive.ngrok-free.dev"
                f"/callback_voice?original_call_sid={original_call_sid}"
            )

            callback_call = twilio_client.calls.create(
                to=customer_phone,
                from_=os.getenv("TWILIO_PHONE_NUMBER"),
                url=callback_url
            )

            print("  CALLBACK CREATED")
            print("Customer:", customer_phone)
            print("New Call SID:", callback_call.sid)
            print("Original Call SID:", original_call_sid)

        except Exception as e:

            print(" CALLBACK ERROR:")
            print(e)

    threading.Thread(
        target=make_callback,
        daemon=True
    ).start()

    

@app.post("/process_speech")
async def process_speech(request: Request):
    form_data = await request.form()
    speech = form_data.get("SpeechResult")
    print("CUSTOMER SAID:", speech)
    call_sid = form_data.get("CallSid")
    print(call_sid)


    if call_sid not in customers:
        customers[call_sid] = {
            "language": None,
            "business": None,
            "website_type": None,
            "products": None,
            "budget": None,
            "timeline": None,
            "features": [],
            "intent" : None,
            "lead_score" : 0,
            "lead_status" : "COLD",
            "customer_phone": "+919026893667",
            "whatsapp_sent": False,
            "hot_action_sent": False,

            "callback_requested": False,
            "callback_time": None,
            "callback_scheduled": False,
        }

    customer = customers[call_sid]

    ai_response = get_ai_response(speech, customer)

    busy = customer_is_busy(speech)

    if busy and not customer["callback_scheduled"]:

        print("📅 CUSTOMER IS BUSY")
        print("📅 AUTOMATIC CALLBACK FOR TOMORROW")

        schedule_callback_next_day(
            call_sid,
            customer["customer_phone"]
        )

        customer["callback_requested"] = True

        customer["callback_time"] = (
            datetime.now() + timedelta(days=1)
        ).isoformat()

        customer["callback_scheduled"] = True


    try:
        data = json.loads(ai_response)
    except json.JSONDecodeError:

        print("ERROR: AI RETURNED INVALID JSON")

        twiml = """
        <Response>

            <Say>
                Sorry, could you please repeat that?
            </Say>

            <Gather
                input="speech"
                action="https://effects-galvanize-defensive.ngrok-free.dev/process_speech"
                method="POST"
                speechTimeout="5"
                speechModel="deepgram_nova-3"
                language="multi">
            </Gather>

        </Response>
        """

        return Response(
            content=twiml,
            media_type="application/xml"
        )


    # GET AI DATA

    updated_info = data.get(
        "updated_info",
        {}
    )

    ai_response = data.get(
        "response",
        "Could you please tell me more?"
    )

    end_call = data.get(
        "end_call",
        False
    )

    if busy:
        end_call = True


 # AUTOMATIC CALLBACK IF CUSTOMER IS BUSY


    busy = customer_is_busy(speech)

    if busy and not customer["callback_scheduled"]:

            print(" CUSTOMER IS BUSY")
            print(" CALLBACK WILL HAPPEN TOMORROW")

            schedule_callback_next_day(
                call_sid,
                customer["customer_phone"]
            )

            customer["callback_requested"] = True

            customer["callback_time"] = (
                datetime.now() + timedelta(days=1)
            ).isoformat()

            customer["callback_scheduled"] = True

            print(" CALLBACK SCHEDULED FOR TOMORROW")



    # UPDATE CUSTOMER MEMORY

    for key, value in updated_info.items():

        if key not in customer:
            continue

        if value is None:
            continue


      

        if key == "features":

            if isinstance(value, list):

                for feature in value:

                    if feature not in customer["features"]:

                        customer["features"].append(feature)


        else:

            customer[key] = value


    lead_score = calculate_lead_score(customer)
    lead_status = classify_lead(
        lead_score
    )

    customer["lead_score"] = lead_score

    customer["lead_status"] = lead_status

    if (customer["lead_status"] == "WARM" and not customer["hot_action_sent"]):

        print("🔥 LEAD BECAME HOT")

        whatsapp_sent = send_hot_lead_whatsapp(customer)

        if whatsapp_sent:
            customer["hot_action_sent"] = True
            print("✅ hot_action_sent = True")
        else:
            customer["hot_action_sent"] = False
            print("❌ WhatsApp failed, hot_action_sent remains False")


    # PRINT MEMORY

    print("\nCURRENT CUSTOMER MEMORY:")

    print(
        json.dumps(
            customer,
            ensure_ascii=False,
            indent=4
        )
    )


    print("\nAI RESPONSE:")

    print(ai_response)
    print("\nEND CALL:", end_call)

    print("LEAD SCORE:", lead_score)

    print("LEAD STATUS:", lead_status)

    # SEND RESPONSE TO TWILIO

    if end_call:

        twiml = f"""
        <Response>

            <Say>
                {ai_response}
            </Say>

            <Hangup/>

        </Response>
        """

    else :
        twiml = f"""
        <Response>

            <Say>
                {ai_response}
            </Say>

            <Gather
                input="speech"
                action="https://effects-galvanize-defensive.ngrok-free.dev/process_speech"
                method="POST"
                speechTimeout="5"
                speechModel="deepgram_nova-3"
                language="multi">
            </Gather>

        </Response>
        """

    return Response(
        content=twiml,
        media_type="application/xml"
    )
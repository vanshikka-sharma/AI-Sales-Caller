from fastapi import FastAPI, Request
from fastapi.responses import Response
from langchain_openai import ChatOpenAI
import json
from prompt import SYSTEM_PROMPT
import re

customers = {}

app = FastAPI()

model = ChatOpenAI(model="gpt-4o-mini")

@app.post("/voice")
async def voice():
    twiml = """
    <Response>
        <Say>Hello are you looking for a website?</Say>
        <Gather input="speech" action="https://effects-galvanize-defensive.ngrok-free.dev/process_speech"  method="POST" speechTimeout="5" speechModel="deepgram_nova-3" language="multi"></Gather>
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
            "features": []
        }

    customer = customers[call_sid]

    ai_response = get_ai_response(speech, customer)


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


    # ======================================
    # GET AI DATA
    # ======================================

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

    # ======================================
    # UPDATE CUSTOMER MEMORY
    # ======================================

    for key, value in updated_info.items():

        if key not in customer:
            continue

        if value is None:
            continue


        # FEATURES

        if key == "features":

            if isinstance(value, list):

                for feature in value:

                    if feature not in customer["features"]:

                        customer["features"].append(feature)


        # NORMAL FIELDS

        else:

            customer[key] = value


    # ======================================
    # PRINT MEMORY
    # ======================================

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


    # ======================================
    # SEND RESPONSE TO TWILIO
    # ======================================

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
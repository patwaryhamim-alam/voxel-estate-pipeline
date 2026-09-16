import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

try:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("API key pawa jay ni! .env file check koro.")

    llm = ChatGoogleGenerativeAI(
        model="gemini-3.5-flash",
        google_api_key=api_key
    )
    response = llm.invoke("Reply in one short line: Hello, are you working?")
    print("SUCCESS! Gemini boleche:")
    print(response.text)

except Exception as e:
    print(f"ERROR hoyeche: {e}")
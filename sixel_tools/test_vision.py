from dotenv import load_dotenv
load_dotenv()

from google.cloud import vision

client = vision.ImageAnnotatorClient()
print("✅ Vision client OK")

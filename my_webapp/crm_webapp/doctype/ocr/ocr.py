
import frappe
from frappe.model.document import Document
import requests
import json
import base64
import os

# Put your OpenAI key here
OPENAI_API_KEY = "Open AI Api Key" 

class OCR(Document):
    pass

@frappe.whitelist()
def fetch_from_ai(docname: str):

    # Load the OCR document
    doc = frappe.get_doc("OCR", docname)

    if not doc.upload_file:
        frappe.throw("Please upload a PDF or Image first and save the document.")

    # Fetch the attached file
    file_doc = frappe.get_doc("File", {"file_url": doc.upload_file})
    file_path = file_doc.get_full_path()
    file_name = file_doc.file_name

    # Detect file extension
    ext = os.path.splitext(file_name)[1].lower()

    #---------------------------------------------------------
    # CASE 1: IMAGE (png, jpg, jpeg) → Convert to Base64
    #---------------------------------------------------------
    if ext in [".png", ".jpg", ".jpeg"]:

        # Read file as base64
        with open(file_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")

        # Set correct MIME type
        mime = "image/png" if ext == ".png" else "image/jpeg"

        # Prepare extract payload for image
        extract_payload = {
            "model": "gpt-4.1-mini", 
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Extract all fields from this PDF and return ONLY pure JSON. "
                                "Do NOT include markdown. Do NOT include backticks." 
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:{mime};base64,{encoded}"
                        }
                    ]
                }
            ]
        }

    #---------------------------------------------------------
    # CASE 2: PDF → Use your original logic
    #---------------------------------------------------------
    else:

        # Read PDF file bytes
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        # Upload PDF to OpenAI → get file_id
        upload_resp = requests.post(
            "https://api.openai.com/v1/files",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            data={"purpose": "assistants"},
            files={"file": (file_name, file_bytes, "application/pdf")}
        )

        upload_resp.raise_for_status()
        file_id = upload_resp.json().get("id")

        # Original extract payload for PDF
        extract_payload = {
            "model": "gpt-4.1-mini", 
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_file", "file_id": file_id},
                        {
                            "type": "input_text",
                            "text": (
                                "Extract all fields from this PDF and return ONLY pure JSON. "
                                "Do NOT include markdown. Do NOT include backticks."
                            )
                        }
                    ]
                }
            ]
        }

    #---------------------------------------------------------
    # STEP 2: Send request to /v1/responses
    #---------------------------------------------------------

    extract_resp = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        },
        json=extract_payload
    )

    extract_resp.raise_for_status()
    data = extract_resp.json()

    # Extract JSON text
    result_text = data["output"][0]["content"][0]["text"]

    # Save output into json_content field
    doc.json_content = result_text
    doc.save()
    frappe.db.commit()

    return {"status": "success", "json": result_text}



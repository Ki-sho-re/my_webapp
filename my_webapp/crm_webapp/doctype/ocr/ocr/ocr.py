import frappe
from frappe.model.document import Document
import requests
import json

# Put your OpenAI key here
#OPENAI_API_KEY = "OpenAI APi Key"
api_key = frappe.conf.get("OPENAI_API_KEY") 
class OCR(Document):
    pass

@frappe.whitelist()
def fetch_from_ai(docname: str):

    # Load the OCR document
    doc = frappe.get_doc("OCR", docname)

    if not doc.upload_file:
        frappe.throw("Please upload a PDF first and save the document.")

    # Fetch the attached file
    file_doc = frappe.get_doc("File", {"file_url": doc.upload_file})
    file_path = file_doc.get_full_path()
    file_name = file_doc.file_name or "document.pdf"

    # Read file
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    # STEP 1: Upload PDF to OpenAI → get file_id
    upload_resp = requests.post(
        "https://api.openai.com/v1/files",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        data={"purpose": "assistants"},
        files={"file": (file_name, file_bytes, "application/pdf")}
    )

    upload_resp.raise_for_status()
    file_id = upload_resp.json().get("id")

    # STEP 2: Request JSON extraction using /v1/responses
    extract_payload = {
        "model": "gpt-4o-mini",
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

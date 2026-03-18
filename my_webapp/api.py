import frappe
import json
import base64
from io import BytesIO
from frappe.utils import get_site_path
from frappe.utils.file_manager import save_file
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from datetime import datetime
from PIL import Image
from os.path import basename, splitext






@frappe.whitelist()
def send_signed_document(docname):
    import frappe

    doc = frappe.get_doc("Upload File", docname)

    # --------------------------------
    # Validations
    # --------------------------------
    if not doc.recipient:
        frappe.throw("Recipient email is required")

    if not doc.subject:
        frappe.throw("Email subject is required")

    if not doc.body:
        frappe.throw("Email body is required")

    if not doc.doc:
        frappe.throw("Signed document not found")

    # --------------------------------
    # Recipients
    # --------------------------------
    recipients = [e.strip() for e in doc.recipient.split(",") if e.strip()]

    cc = []
    if doc.cc:
        cc = [e.strip() for e in doc.cc.split(",") if e.strip()]

    # --------------------------------
    # Attach using file_url (KEY FIX)
    # --------------------------------
    attachments = [
        {
            "file_url": doc.doc
        }
    ]

    # --------------------------------
    # Send email
    # --------------------------------
    frappe.sendmail(
        recipients=recipients,
        cc=cc,
        subject=doc.subject,
        message=doc.body,
        attachments=attachments
    )

    frappe.db.commit()

    return "Email sent successfully with attachment"














@frappe.whitelist()
def finalize_sign(docname, signature):

    doc = frappe.get_doc("Upload File", docname)

    if not doc.document_pdf:
        frappe.throw("Source PDF not found")

    # ------------------------------------------------
    # Resolve PDF path
    # ------------------------------------------------
    file_url = doc.document_pdf

    if file_url.startswith("/private/files/"):
        pdf_path = get_site_path(
            "private", file_url.replace("/private/files/", "files/")
        )
    else:
        pdf_path = get_site_path(
            "public", file_url.replace("/files/", "files/")
        )

    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    # ------------------------------------------------
    # Load signature image
    # ------------------------------------------------
    if signature.startswith("data:image"):
        img_data = base64.b64decode(signature.split(",", 1)[1])
        sig_img = Image.open(BytesIO(img_data)).convert("RGBA")
    else:
        sig_path = get_site_path("public", signature.lstrip("/"))
        sig_img = Image.open(sig_path).convert("RGBA")

    # ------------------------------------------------
    # Placement data
    # ------------------------------------------------
    page_index = int(doc.signature_page) - 1
    x = float(doc.signature_x)
    y = float(doc.signature_y)
    w = float(doc.signature_width)
    h = float(doc.signature_height)

    canvas_w = float(doc.canvas_width)
    canvas_h = float(doc.canvas_height)

    target_page = reader.pages[page_index]

    pdf_w = float(target_page.mediabox.width)
    pdf_h = float(target_page.mediabox.height)

    # Canvas → PDF scaling
    scale_x = pdf_w / canvas_w
    scale_y = pdf_h / canvas_h

    pdf_x = x * scale_x
    pdf_y = (canvas_h - y - h) * scale_y
    pdf_w_sig = w * scale_x
    pdf_h_sig = h * scale_y

    # ------------------------------------------------
    # Create overlay PDF
    # ------------------------------------------------



    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(pdf_w, pdf_h))

    # Save signature image to buffer
    img_buf = BytesIO()
    sig_img.save(img_buf, format="PNG")
    img_buf.seek(0)

    # Draw signature image
    c.drawImage(
      ImageReader(img_buf),
      pdf_x,
      pdf_y,
      pdf_w_sig,
      pdf_h_sig,
      mask="auto"
    )

# ------------------------------------------------
# Draw date & time under signature
# ------------------------------------------------
    sign_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    c.setFont("Helvetica", 9)
    c.setFillColorRGB(0, 0, 0)

# 10 px below signature
    c.drawString(
      pdf_x,
      pdf_y - 12,
      f"Signed on: {sign_time}"
    )

    c.save()
    packet.seek(0)
    overlay = PdfReader(packet).pages[0]

    # ------------------------------------------------
    # Merge pages
    # ------------------------------------------------
    for i, page in enumerate(reader.pages):
        if i == page_index:
            page.merge_page(overlay)
        writer.add_page(page)

    # ------------------------------------------------
    # Save final PDF
    # ------------------------------------------------
    output = BytesIO()
    writer.write(output)

    original_url = doc.document_pdf
    original_filename = basename(original_url)
    name_without_ext, _ = splitext(original_filename)
    date_str = datetime.now().strftime("%Y-%m-%d")
    file_name = f"{name_without_ext}_signed_{date_str}.pdf"

    #file_name = f"{docname}_signed_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"

    signed_file = save_file(
        file_name,
        output.getvalue(),
        doc.doctype,
        doc.name,
        is_private=0
    )

    # IMPORTANT: no version conflict
    frappe.db.set_value(
        "Upload File",
        docname,
        "doc",
        signed_file.file_url,
        update_modified=False
    )

    frappe.db.commit()

    return signed_file.file_url







#It Set the postion in the Upload File Doctype 
@frappe.whitelist()
def save_signature_position(docname, field_data):
    data = json.loads(field_data)

    doc = frappe.get_doc("Upload File", docname)

    doc.signature_page = data.get("page", 0)
    doc.signature_x = data["x"]
    doc.signature_y = data["y"]
    doc.signature_width = data["width"]
    doc.signature_height = data["height"]
    doc.canvas_width = data.get("canvas_width", 0)
    doc.canvas_height = data.get("canvas_height", 0)

    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "ok", "saved": True}


@frappe.whitelist()
def generate_esign_pdf(docname):
    doc = frappe.get_doc("Upload File", docname)

    if not doc.document_pdf:
        frappe.throw("Original PDF not found")

    file_url = doc.document_pdf
    if file_url.startswith("/private/files/"):
        pdf_path = get_site_path("private", file_url.replace("/private/files/", "files/"))
    else:
        pdf_path = get_site_path("public", file_url.replace("/files/", "files/"))

    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    page_index = doc.signature_page - 1

    target_page = reader.pages[page_index]
    pdf_width = float(target_page.mediabox.width)
    pdf_height = float(target_page.mediabox.height)

    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(pdf_width, pdf_height))

    c.setFont("Helvetica-Oblique", 10)
    c.drawString(
        doc.signature_x + 5,
        pdf_height - doc.signature_y - doc.signature_height + 5,
        "(e-sign)"
    )

    c.save()
    packet.seek(0)

    overlay_pdf = PdfReader(packet)

    for i, page in enumerate(reader.pages):
        if i == page_index:
            page.merge_page(overlay_pdf.pages[0])
        writer.add_page(page)

    output = BytesIO()
    writer.write(output)

    signed_file = save_file(
        f"{docname}_esign.pdf",
        output.getvalue(),
        doc.doctype,
        doc.name,
        is_private=0
    )

    doc.doc = signed_file.file_url
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"file_url": signed_file.file_url}










#It set the Signature Position for Sign Here

@frappe.whitelist()
def generate_esign_pdfke(docname):
    doc = frappe.get_doc("Sign Here", docname)

    if not doc.document_pdf:
        frappe.throw("Original PDF not found")

    # Resolve PDF path
    file_url = doc.document_pdf
    if file_url.startswith("/private/files/"):
        pdf_path = get_site_path("private", file_url.replace("/private/files/", "files/"))
    else:
        pdf_path = get_site_path("public", file_url.replace("/files/", "files/"))

    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    page_index = doc.signature_page - 1  # convert to 0-based

    # Target page size
    target_page = reader.pages[page_index]
    pdf_width = float(target_page.mediabox.width)
    pdf_height = float(target_page.mediabox.height)

    # Create overlay
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(pdf_width, pdf_height))

    c.setFont("Helvetica-Oblique", 10)
    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.drawString(
        doc.signature_x + 5,
        pdf_height - doc.signature_y - doc.signature_height + 5,
        "(e-sign)"
    )

    c.save()
    packet.seek(0)

    overlay_pdf = PdfReader(packet)

    for i, page in enumerate(reader.pages):
        if i == page_index:
            page.merge_page(overlay_pdf.pages[0])
        writer.add_page(page)

    # Write final PDF
    output = BytesIO()
    writer.write(output)

    signed_file = save_file(
        f"{docname}_esign.pdf",
        output.getvalue(),
        doc.doctype,
        doc.name,
        is_private=0
    )

    # Attach to field `doc`
    doc.doc = signed_file.file_url
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "file_url": signed_file.file_url
    }





#It Set the Signature Position 

@frappe.whitelist()
def save_signature_positionke(docname, field_data):

    data = json.loads(field_data)

    # VERY IMPORTANT: confirm doctype name
    doc = frappe.get_doc("Sign Here", docname)

    # Save all values
    doc.signature_page = data.get("page", 0)
    doc.signature_x = data["x"]
    doc.signature_y = data["y"]
    doc.signature_width = data["width"]
    doc.signature_height = data["height"]
    doc.canvas_width = data.get("canvas_width", 0)
    doc.canvas_height = data.get("canvas_height", 0)

    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "ok", "saved": True}















# ======================================================
# PDF PREVIEW (USED BY PDF.js)
# ======================================================
@frappe.whitelist(allow_guest=True)
def get_pdf_binary(docname):
    if not docname:
        frappe.throw("Invalid request")

    doc = frappe.get_doc("Sign Here", docname)

    if not doc.document_pdf:
        frappe.throw("PDF not found")

    file_url = doc.document_pdf

    if file_url.startswith("/private/files/"):
        file_path = get_site_path("private", file_url.replace("/private/files/", "files/"))
    else:
        file_path = get_site_path("public", file_url.replace("/files/", "files/"))

    with open(file_path, "rb") as f:
        pdf_bytes = f.read()

    frappe.local.response.type = "binary"
    frappe.local.response.filecontent = pdf_bytes
    frappe.local.response.filename = "document.pdf"
    frappe.local.response.content_type = "application/pdf"


# ======================================================
# FINALIZE SIGNATURE + GENERATE SIGNED PDF
# ======================================================









@frappe.whitelist(allow_guest=True)
def finalize_signature(docname, signatures, mode):
    """
    mode = "dragdrop"   -> drag & drop placement
    mode = "pad"        -> fixed signature pad placement
    """

    if not docname or not signatures or not mode:
        frappe.throw("Invalid request")

    signatures = json.loads(signatures)
    doc = frappe.get_doc("Sign Here", docname)

    if not doc.document_pdf:
        frappe.throw("Original PDF not found")

    # Resolve PDF path
    file_url = doc.document_pdf
    if file_url.startswith("/private/files/"):
        pdf_path = get_site_path("private", file_url.replace("/private/files/", "files/"))
    else:
        pdf_path = get_site_path("public", file_url.replace("/files/", "files/"))

    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    # Decide which method to use
    if mode == "dragdrop":
        writer = apply_drag_drop_signature(reader, signatures)
    elif mode == "pad":
        writer = apply_signature_pad(reader, signatures)
    else:
        frappe.throw("Invalid signing mode")

    # ------------------------------------------------
    # Save signed PDF
    # ------------------------------------------------
    output = BytesIO()
    writer.write(output)
    #date_str = datetime.now().strftime("%Y-%m-%d")

    original_url = doc.document_pdf
    original_filename = basename(original_url)
    name_without_ext, _ = splitext(original_filename)
    date_str = datetime.now().strftime("%Y-%m-%d")
    file_name = f"{name_without_ext}_signed_{date_str}.pdf"

    #file_name = f"{docname}_signed_{date_str}.pdf"

    signed_file = save_file(
       # f"{docname}_signed.pdf",
        file_name,
        output.getvalue(),
        doc.doctype,
        doc.name,
        is_private=0
    )

    doc.signed_pdf = signed_file.file_url
    doc.status = "Signed"
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "signed_pdf": signed_file.file_url
    }










# ------------------------------------------------
# DRAG & DROP SIGNATURE METHOD
# ------------------------------------------------
def apply_drag_drop_signature(reader, signatures):

    writer = PdfWriter()
    sig = signatures[0]

    img_data = sig["image"].split(",", 1)[1]
    img_bytes = base64.b64decode(img_data)

    page_index = int(sig.get("page", 0))

    x = float(sig["x"])
    y = float(sig["y"])
    w = float(sig["width"])
    h = float(sig["height"])

    canvas_w = float(sig["canvas_width"])
    canvas_h = float(sig["canvas_height"])

    target_page = reader.pages[page_index]

    pdf_width = float(target_page.mediabox.width)
    pdf_height = float(target_page.mediabox.height)

    # Scale canvas → PDF
    scale_x = pdf_width / canvas_w
    scale_y = pdf_height / canvas_h

    real_x = x * scale_x
    real_y = (canvas_h - y - h) * scale_y
    real_w = w * scale_x
    real_h = h * scale_y

    # Create overlay
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(pdf_width, pdf_height))
    img_reader = ImageReader(BytesIO(img_bytes))

    #c.drawImage(img_reader, real_x, real_y, real_w, real_h, mask="auto") 
    # Draw signature image
    c.drawImage(img_reader, real_x, real_y, real_w, real_h, mask="auto")
    sign_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    c.setFont("Helvetica", 9)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(real_x, real_y - 12, f"Signed on: {sign_time}")


    c.save()
    packet.seek(0)

    overlay_pdf = PdfReader(packet)
    signed_overlay = overlay_pdf.pages[0]

    # Merge into correct page
    for i in range(len(reader.pages)):
        page = reader.pages[i]

        if i == page_index:
            page.merge_page(signed_overlay)

        writer.add_page(page)

    return writer


# ------------------------------------------------
# SIGNATURE PAD METHOD (fixed placement)
# ------------------------------------------------
def apply_signature_pad(reader, signatures):

    writer = PdfWriter()
    base_page = reader.pages[0]

    sig = signatures[0]
    img_data = sig["image"].split(",", 1)[1]
    img_bytes = base64.b64decode(img_data)

    pdf_width = float(base_page.mediabox.width)
    pdf_height = float(base_page.mediabox.height)

    # Fixed placement
    sig_width = pdf_width * 0.35
    sig_height = sig_width * 0.35

    sig_x = (pdf_width - sig_width) / 2
    sig_y = pdf_height * 0.18

    # Create overlay
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(pdf_width, pdf_height))
    img_reader = ImageReader(BytesIO(img_bytes))

    c.drawImage(img_reader, sig_x, sig_y, sig_width, sig_height, mask="auto")
    c.save()
    packet.seek(0)

    overlay_pdf = PdfReader(packet)
    base_page.merge_page(overlay_pdf.pages[0])

    writer.add_page(base_page)

    
    for i in range(1, len(reader.pages)):
        writer.add_page(reader.pages[i])

    return writer







































# -----------------------------
# GET ALL RECORDS
# -----------------------------
@frappe.whitelist()
def get_all_leads():
    """Return all leads with basic details."""
    return frappe.get_all("Lead", fields=["name", "first_name", "last_name"])

@frappe.whitelist()
def get_all_prospects():
    """Return all prospects with basic details."""
    return frappe.get_all("Prospect", fields=["name", "lead", "status", "prospect_owner"])

# -----------------------------
# GET SINGLE RECORD
# -----------------------------
@frappe.whitelist()
def get_lead_details(name):
    return frappe.get_doc("Lead", name)


@frappe.whitelist()
def get_prospect_details(name):
    """Fetch single Prospect details and include 'name1' mapped from prospect_name."""
    doc = frappe.get_doc("Prospect", name)
    # convert to dict so we can add custom keys that will be serialized to JSON
    data = doc.as_dict()
    # map backend field prospect_name to frontend name1
    data["name1"] = data.get("prospect_name")
    return data

# -----------------------------
# CREATE LEAD
# -----------------------------
@frappe.whitelist(allow_guest=True)
def create_lead(payload):
    """Create or update a Lead record."""
    if isinstance(payload, str):
        import json
        payload = json.loads(payload)

    # If name exists, update instead of duplicate
    lead_name = payload.get("name")
    if lead_name and frappe.db.exists("Lead", lead_name):
        return update_lead(payload)

    required = ["first_name", "email"]
    for r in required:
        if not payload.get(r):
            frappe.throw(_(f"{r} is required"))

    doc = frappe.get_doc({
        "doctype": "Lead",
        "lead_owner": payload.get("lead_owner"),
        "email": payload.get("email"),
        "status": payload.get("status"),
        "first_name": payload.get("first_name"),
        "last_name": payload.get("last_name"),
        "phone": payload.get("phone"),
        "mobile": payload.get("mobile"),
        "lead_source": payload.get("lead_source"),
        "company": payload.get("company"),
        "annual_revenue": payload.get("annual_revenue"),
        "industry": payload.get("industry"),
        "website": payload.get("website"),
        "no_of_employee": payload.get("no_of_employee"),
        "street": payload.get("street"),
        "state": payload.get("state"),
        "country": payload.get("country"),
        "city": payload.get("city"),
        "zipcode": payload.get("zipcode"),
        "description": payload.get("description"),
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"status": "created", "name": doc.name}

# -----------------------------
# UPDATE LEAD
# -----------------------------
@frappe.whitelist(allow_guest=True)
def update_lead(payload):
    """Update existing Lead record."""
    if isinstance(payload, str):
        import json
        payload = json.loads(payload)

    lead_name = payload.get("name")
    if not lead_name:
        frappe.throw(_("Lead name is required for update"))

    doc = frappe.get_doc("Lead", lead_name)
    for key, value in payload.items():
        if hasattr(doc, key) and key not in ["doctype", "name"]:
            setattr(doc, key, value)
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"status": "updated", "name": doc.name}

# -----------------------------
# CREATE PROSPECT
# -----------------------------
@frappe.whitelist(allow_guest=True)
def create_prospect(payload):
    """Create Prospect from Prospect form."""
    if isinstance(payload, str):
        import json
        payload = json.loads(payload)

    required = ["status"]
    for r in required:
        if not payload.get(r):
            frappe.throw(_(f"{r} is required"))

    doc = frappe.get_doc({
        "doctype": "Prospect",
        "prospect_name": payload.get("name1"),
        "email" : payload.get("email"),
         "phone" : payload.get("phone"),
        "status": payload.get("status"),
        "prospect_owner": payload.get("prospect_owner"),
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"status": "created", "name": doc.name}

# -----------------------------
# CONVERT LEAD TO PROSPECT
# -----------------------------
@frappe.whitelist(allow_guest=True)
def convert_lead_to_prospect(lead_name):
    """Convert a Lead to a Prospect (only if status = Converted)."""
    lead = frappe.get_doc("Lead", lead_name)
    if not lead:
        frappe.throw(_("Lead not found"))

    if lead.status != "Converted":
        return {"status": "not_converted", "msg": "Lead is not yet converted"}

    # Check if already exists
    exists = frappe.get_all("Prospect", filters={"lead": lead.name})
    if exists:
        return {"status": "exists", "name": exists[0].name}

    # Create Prospect
    doc = frappe.get_doc({
        "doctype": "Prospect",
        "lead": lead.name,
        "status": "Interested",
        "prospect_owner": lead.lead_owner
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"status": "created", "name": doc.name}





# -----------------------------
# UPDATE PROSPECT
# -----------------------------
@frappe.whitelist(allow_guest=True)
def update_prospect(payload):
    """Update existing Prospect record."""
    if isinstance(payload, str):
        import json
        payload = json.loads(payload)

    # Prospect 'name' is the internal document ID, not name1
    prospect_name = payload.get("name")
    if not prospect_name:
        frappe.throw(_("Prospect name is required for update"))

    doc = frappe.get_doc("Prospect", prospect_name)

    # Update only the same fields you use in create_prospect
    if payload.get("prospect_name"):
        doc.prospect_name = payload.get("prospect_name")
    if payload.get("email"):
        doc.email = payload.get("email")
    if payload.get("phone"):
        doc.phone = payload.get("phone")
    if payload.get("status"):
        doc.status = payload.get("status")
    if payload.get("prospect_owner"):
        doc.prospect_owner = payload.get("prospect_owner")

    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"status": "updated", "name": doc.name}










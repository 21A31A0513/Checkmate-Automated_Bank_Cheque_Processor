import streamlit as st
import auth  # Import the external authentication logic
import fitz
import io
from PIL import Image
import base64
import json
import re
import pandas as pd
from fpdf import FPDF
import hashlib  # To compute a unique identifier for uploaded files
from google.generativeai import configure, GenerativeModel

# Function to extract images from PDF
def extract_images(pdf_path):
    doc = fitz.open(pdf_path)
    images = []
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        page_images = page.get_images(full=True)
        for img in page_images:
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image = Image.open(io.BytesIO(image_bytes))
            images.append(image)
    return images

def encode_image(image):
    with io.BytesIO() as buffer:
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

def extract_cheque_details(image, api_key):
    encoded_image = encode_image(image)
    prompt = (
        "You are provided with an image of a bank cheque. Extract the following details:\n"
        "- Bank Name\n"
        "- Bank Address\n"
        "- Bank IFSC Code\n"
        "- Payee Name\n"
        "- Amount\n"
        "- Date\n"
        "- Account Number\n"
        "Return the extracted details in JSON format."
    )
    try:
        configure(api_key=api_key)
        model = GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(
            [prompt, {"mime_type": "image/png", "data": encoded_image}]
        )
        text = response.text.strip()
        cleaned_text = re.sub(r"```json|\n```", "", text).strip()
        return json.loads(cleaned_text)
    except Exception as e:
        st.error(f"Error extracting cheque details: {e}")
        return None

def compute_file_hash(file):
    """Compute a unique hash for the uploaded file."""
    file.seek(0)  # Reset file pointer
    file_hash = hashlib.md5(file.read()).hexdigest()
    file.seek(0)  # Reset file pointer again after hashing
    return file_hash

def main():
    st.sidebar.header("Authentication")
    st.title("Welcome to Checkmate: Automated Bank Cheque Processor")

    st.markdown(
        """
        **Checkmate** is a powerful tool designed to streamline the process of extracting 
        and managing information from scanned bank cheques. With the help of this application, you can:
        
        - Upload scanned cheques or PDF files.
        - Automatically extract details such as Bank Name, IFSC Code, Payee Name, Amount, Date, and Account Number.
        - Review extracted data in an organized table format.
        - Download extracted details as Excel or PDF files for further processing.
        
        **Get started by logging in or registering an account to begin processing cheques!**
        """
    )

    # Initialize session states
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "show_success" not in st.session_state:
        st.session_state.show_success = False
    if "processed_files" not in st.session_state:
        st.session_state.processed_files = {}  # To store already processed files
    if "cheque_df" not in st.session_state:
        st.session_state.cheque_df = pd.DataFrame()

    if not st.session_state.logged_in:
        choice = st.sidebar.radio("Choose an option", ["Login", "Register"])

        if choice == "Register":
            username = st.sidebar.text_input("Username")
            password = st.sidebar.text_input("Password", type="password")
            if st.sidebar.button("Register"):
                if username and password:
                    if auth.register_user(username, password):
                        st.sidebar.success("User Registered Successfully, Now you can Login")
                    else:
                        st.sidebar.error("Username already exists!")
                else:
                    st.sidebar.error("Enter all fields")

        elif choice == "Login":
            username = st.sidebar.text_input("Username")
            password = st.sidebar.text_input("Password", type="password", autocomplete="off")
            if st.sidebar.button("Login"):
                if username and password:
                    if auth.authenticate_user(username, password):
                        st.session_state.logged_in = True
                        st.session_state.show_success = True  # Set the transient success state
                        st.experimental_rerun()  # Trigger rerun to display success message
                    else:
                        st.sidebar.error("Invalid credentials")
                else:
                    st.sidebar.error("Enter all fields")
    else:
        # Show success message briefly after login
        if st.session_state.show_success:
            st.sidebar.success("Logged in successfully!")
            st.session_state.show_success = False  # Clear success state after display
            st.experimental_rerun()  # Rerun app to transition from success message

        # Logout button
        st.sidebar.success("Logged in!")
        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.cheque_df = pd.DataFrame()
            st.experimental_rerun()

    # Main content for logged-in users
    if st.session_state.logged_in:
        uploaded_file = st.file_uploader("Upload a PDF or cheque image", type=["pdf", "png", "jpg"])
        
        if uploaded_file:
            file_hash = compute_file_hash(uploaded_file)
            
            if file_hash in st.session_state.processed_files:
                st.success("File has already been processed!")
                st.write("### Extracted Cheque Details")
                st.table(st.session_state.cheque_df)
            else:
                st.success("Processing uploaded file...")
                cheque_images = []
                if uploaded_file.name.endswith(".pdf"):
                    cheque_images = extract_images(uploaded_file)
                else:
                    cheque_images.append(Image.open(uploaded_file))

                if cheque_images:
                    for img in cheque_images:
                        details = extract_cheque_details(img, "AIzaSyDmpWBYY81TLVQwoM17WgtHWp0MJs-ZD-0")
                        if details:
                            st.session_state.cheque_df = pd.concat(
                                [st.session_state.cheque_df, pd.DataFrame([details])], ignore_index=True
                            )
                    
                    # Mark file as processed
                    st.session_state.processed_files[file_hash] = True

                    st.write("### Extracted Cheque Details")
                    st.table(st.session_state.cheque_df)

        # Download options
        if not st.session_state.cheque_df.empty:
            st.header("Download Options")
            
            # Excel download
            excel_output = io.BytesIO()
            with pd.ExcelWriter(excel_output, engine='xlsxwriter') as writer:
                st.session_state.cheque_df.to_excel(writer, index=False, sheet_name="Cheque Details")
            st.download_button(
                label="Download as Excel",
                data=excel_output.getvalue(),
                file_name="cheque_details.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            
            # PDF download
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=10)
            for index, row in st.session_state.cheque_df.iterrows():
                pdf.multi_cell(190, 10, txt=str(row.to_dict()), border=1)
                pdf.ln()
            pdf_output = io.BytesIO()
            pdf_output.write(pdf.output(dest="S").encode('latin-1'))
            pdf_output.seek(0)
            st.download_button(
                label="Download as PDF",
                data=pdf_output,
                file_name="cheque_details.pdf",
                mime="application/pdf"
            )
    else:
        st.warning("Please log in to use the app.")

if __name__ == "__main__":
    main()

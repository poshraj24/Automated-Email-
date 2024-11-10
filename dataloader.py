# app.py
import streamlit as st
from pydantic import BaseModel, EmailStr
from typing import List, Optional
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import json
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import traceback


# Pydantic Models
class EmailConfig(BaseModel):
    sender_email: EmailStr
    sender_password: str
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587


class Notification(BaseModel):
    topic: str
    frequency: str  # instant, daily, weekly, monthly
    last_sent: Optional[datetime] = None


class Recipient(BaseModel):
    email: EmailStr
    topics: List[str] = []
    notifications: List[Notification] = []


# Google Sheets Integration
def load_topics_from_sheets(sheet_url):
    try:
        # Define the scope
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/spreadsheets",
        ]

        # Load credentials from streamlit secrets
        credentials = {
            "type": st.secrets["gcp_service_account"]["type"],
            "project_id": st.secrets["gcp_service_account"]["project_id"],
            "private_key_id": st.secrets["gcp_service_account"]["private_key_id"],
            "private_key": st.secrets["gcp_service_account"]["private_key"],
            "client_email": st.secrets["gcp_service_account"]["client_email"],
            "client_id": st.secrets["gcp_service_account"]["client_id"],
            "auth_uri": st.secrets["gcp_service_account"]["auth_uri"],
            "token_uri": st.secrets["gcp_service_account"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["gcp_service_account"][
                "auth_provider_x509_cert_url"
            ],
            "client_x509_cert_url": st.secrets["gcp_service_account"][
                "client_x509_cert_url"
            ],
        }

        # Authenticate with Google
        creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials, scope)
        client = gspread.authorize(creds)

        # Extract spreadsheet ID from URL
        if "spreadsheets/d/" in sheet_url:
            sheet_id = sheet_url.split("spreadsheets/d/")[1].split("/")[0]
        else:
            sheet_id = sheet_url

        st.write(f"Attempting to access sheet with ID: {sheet_id}")

        # Open the spreadsheet
        try:
            sheet = client.open_by_key(sheet_id).sheet1
        except Exception as e:
            st.error(f"Error opening sheet: {str(e)}")
            st.error(
                "Please make sure you've shared the sheet with the service account email"
            )
            return []

        # Get all values from the sheet
        data = sheet.get_all_values()

        if not data:
            st.warning("The sheet appears to be empty")
            return []

        # Convert to pandas DataFrame
        df = pd.DataFrame(data[1:], columns=data[0])  # Assuming first row is headers

        if len(df.columns) < 3:
            st.error(
                f"Sheet has fewer than 3 columns. Found columns: {df.columns.tolist()}"
            )
            return []

        # Get unique values from third column (index 2)
        topics = df.iloc[:, 2].dropna().unique().tolist()

        st.success(f"Successfully loaded {len(topics)} topics")
        return topics

    except Exception as e:
        st.error(f"Error loading topics from Google Sheets: {str(e)}")
        st.error(f"Detailed error: {traceback.format_exc()}")
        return []


# Data Management
def load_data():
    if os.path.exists("data.json"):
        with open("data.json", "r") as f:
            data = json.load(f)
            return data.get("recipients", []), data.get("topics", [])
    return [], []


def save_data(recipients, topics):
    with open("data.json", "w") as f:
        json.dump({"recipients": recipients, "topics": topics}, f)


# Email Functions
def send_email(config: EmailConfig, recipient: str, subject: str, body: str):
    try:
        msg = MIMEMultipart()
        msg["From"] = config.sender_email
        msg["To"] = recipient
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(config.smtp_server, config.smtp_port) as server:
            server.starttls()
            server.login(config.sender_email, config.sender_password)
            server.send_message(msg)

        return True
    except Exception as e:
        st.error(f"Error sending email: {str(e)}")
        return False


def send_instant_email(config: EmailConfig, recipient_email: str, topic: str):
    try:
        # Create email subject and body
        subject = f"Notification Update: {topic}"
        body = f"""
Dear Subscriber,

This is an instant notification update for the topic: {topic}.

Time sent: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Best regards,
Notification System
        """

        # Send the email
        success = send_email(config, recipient_email, subject, body)

        if success:
            st.success(
                f"Instant email sent successfully to {recipient_email} for topic: {topic}"
            )
            return True
        else:
            st.error(
                f"Failed to send instant email to {recipient_email} for topic: {topic}"
            )
            return False

    except Exception as e:
        st.error(f"Error sending instant email: {str(e)}")
        return False


# Streamlit UI
def main():
    st.title("Email Notification System")

    # Initialize session state
    if "recipients" not in st.session_state:
        st.session_state.recipients, st.session_state.topics = load_data()

    # Sidebar - Email Configuration
    with st.sidebar:
        st.header("Email Configuration")
        sender_email = st.text_input("Sender Email")
        sender_password = st.text_input("App Password", type="password")

        if sender_email and sender_password:
            config = EmailConfig(
                sender_email=sender_email, sender_password=sender_password
            )

    # Main Content
    tab1, tab2, tab3 = st.tabs(["Recipients", "Topics", "Notifications"])

    # Recipients Tab
    with tab1:
        st.header("Manage Recipients")

        # Add new recipient
        new_email = st.text_input("Add New Recipient Email")
        if st.button("Add Recipient") and new_email:
            try:
                recipient = Recipient(email=new_email)
                st.session_state.recipients.append(recipient.dict())
                save_data(st.session_state.recipients, st.session_state.topics)
                st.success("Recipient added successfully!")
            except Exception as e:
                st.error(f"Error adding recipient: {str(e)}")

        # List and remove recipients
        st.subheader("Current Recipients")
        for i, recipient in enumerate(st.session_state.recipients):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(recipient["email"])
            with col2:
                if st.button("Remove", key=f"remove_{i}"):
                    st.session_state.recipients.pop(i)
                    save_data(st.session_state.recipients, st.session_state.topics)
                    st.rerun()

    # Topics Tab
    with tab2:
        st.header("Manage Topics")

        # Input for Google Sheets URL or ID
        sheets_input = st.text_input(
            "Enter Google Sheets URL or ID",
            "1UOkiD82jEluQK6ZRmtTfxjr1Tgi9ZAKgls_ygq-bzE8",
        )

        if st.button("Load Topics") and sheets_input:
            with st.spinner("Loading topics from Google Sheets..."):
                topics = load_topics_from_sheets(sheets_input)
                if topics:
                    st.session_state.topics = topics
                    save_data(st.session_state.recipients, st.session_state.topics)
                    st.success(f"Successfully loaded {len(topics)} topics!")

                    # Display current topics
                    st.subheader("Current Topics")
                    for topic in st.session_state.topics:
                        st.write(topic)

    # Notifications Tab
    with tab3:
        st.header("Manage Notifications")

        # Select recipient
        recipient_emails = [r["email"] for r in st.session_state.recipients]
        selected_recipient = st.selectbox("Select Recipient", recipient_emails)

        if selected_recipient:
            recipient_idx = recipient_emails.index(selected_recipient)
            recipient = st.session_state.recipients[recipient_idx]

            # Select topics
            selected_topics = st.multiselect(
                "Select Topics",
                st.session_state.topics,
                default=recipient.get("topics", []),
            )

            # Update topics for recipient
            if st.button("Update Topics"):
                st.session_state.recipients[recipient_idx]["topics"] = selected_topics
                save_data(st.session_state.recipients, st.session_state.topics)
                st.success("Topics updated successfully!")

            # Manage notifications
            st.subheader("Notification Schedule")
            for topic in selected_topics:
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    st.write(topic)
                with col2:
                    frequency = st.selectbox(
                        "Frequency",
                        ["instant", "daily", "weekly", "monthly"],
                        key=f"freq_{topic}",
                    )
                with col3:
                    # Add instant send button
                    if frequency == "instant":
                        if st.button("Send Now", key=f"send_{topic}"):
                            if "config" in locals():
                                send_instant_email(config, selected_recipient, topic)
                            else:
                                st.error(
                                    "Please configure email settings in the sidebar first"
                                )

                # Update notifications
                notifications = recipient.get("notifications", [])
                notification_exists = False

                for i, n in enumerate(notifications):
                    if n["topic"] == topic:
                        notifications[i] = Notification(
                            topic=topic,
                            frequency=frequency,
                            last_sent=(
                                datetime.now()
                                if frequency == "instant"
                                else n.get("last_sent")
                            ),
                        ).dict()
                        notification_exists = True
                        break

                if not notification_exists:
                    notifications.append(
                        Notification(
                            topic=topic,
                            frequency=frequency,
                            last_sent=(
                                datetime.now() if frequency == "instant" else None
                            ),
                        ).dict()
                    )

                st.session_state.recipients[recipient_idx][
                    "notifications"
                ] = notifications

            if st.button("Save Notification Settings"):
                save_data(st.session_state.recipients, st.session_state.topics)
                st.success("Notification settings saved successfully!")


if __name__ == "__main__":
    main()

from app.tools.email_extractor import extract_application_record

message = {
    "message_id": "test-1",
    "subject": "We regret to inform you",
    "from": "recruiter@google.com",
    "snippet": "Unfortunately we will not be moving forward.",
    "text": "Thank you for your interest in the Software Engineer position at Google..."
}

record = extract_application_record(message)

print(record)
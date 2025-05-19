import smtplib as smt
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import random
from dotenv import load_dotenv
import traceback

# Load environment variables
load_dotenv()

# Get email configuration from environment variables
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")  # Your email address for sending OTPs
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")  # Your app password for Gmail

def generateOTP(username, usermail):
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        print("Email configuration missing. Check environment variables.")
        print(f"EMAIL_ADDRESS: {EMAIL_ADDRESS}")
        print(f"EMAIL_PASSWORD: {'**REDACTED**' if EMAIL_PASSWORD else 'Missing'}")
        raise ValueError("Email configuration is missing. Please set EMAIL_ADDRESS and EMAIL_PASSWORD environment variables.")
        
    smpt_server = 'smtp.gmail.com'
    smtp_port = 587
    
    msg = MIMEMultipart()
    otp = random.randint(100000, 999999)
    btn = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 0;
                background-color: #f4f4f4;
                text-align: center;
            }}
            .container {{
                width: 90%;
                max-width: 400px;
                margin: 20px auto;
                padding: 20px;
                background-color: #ffffff;
                border-radius: 8px;
                box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
                text-align: center;
            }}
            .bt {{
                display: inline-flex;
                padding: 15px 30px;
                margin-top: 20px;
                border: none;
                font-size: 30px;
                color: #ff4f6c;
                text-decoration: none;
                border-radius: 10px;
                align-items: center;
                justify-content: center;
                text-align: center;
                transition: background 0.3s ease;
            }}
            h3 {{
                font-style: none;
                color: #bfbfbf;
                font-size: 15px;
                margin-bottom: 10px;
            }}
            a{{
                color: white;
            }}
            h5{{
                color: #bfbfbf;
                font-style:none;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h3>Hey {username}, Please use the OTP below to register with StockMind</h3>
            <p class="bt">{otp}</p>
            <h5>If this wasn't you, please ignore the above message</h5>
        </div>
    </body>
    </html>
    """

    msg['From'] = EMAIL_ADDRESS
    msg['To'] = usermail
    msg['Subject'] = "Your OTP for StockMind is here"
    msg['Reply-To'] = EMAIL_ADDRESS
    msg['X-Mailer'] = 'Python-Mail'
    msg.attach(MIMEText(btn, 'html'))

    # Debug email settings
    print(f"SMTP Server: {smpt_server}")
    print(f"SMTP Port: {smtp_port}")
    print(f"From Email: {EMAIL_ADDRESS}")
    print(f"To Email: {usermail}")

    s = smt.SMTP(smpt_server, smtp_port)
    try:
        s.starttls()
        print("SMTP TLS established")
        s.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        print("SMTP Login successful")
        s.sendmail(EMAIL_ADDRESS, usermail, msg.as_string())
        print(f"Email sent successfully to {usermail}")
    except Exception as e:
        print(f"Error sending email: {e}")
        traceback.print_exc()
        raise
    finally:    
        s.quit()
    return otp

def verifyOTP(otp, inp):
    print(f"Verifying OTP - Expected: {otp}, Received: {inp}")
    otp = str(otp)
    inp = str(inp)
    if(otp == inp):
        print("OTP verification successful")
        return True
    else: 
        print("OTP verification failed")
        return False

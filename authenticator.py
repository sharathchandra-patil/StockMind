import smtplib as smt
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import random
import time
from typing import Tuple

#website owner will store their gmail application key 
#in environemnt variable named EMPS and 
#gmail address in env var named owner_email
def generateOTP(username, usermail):
    smpt_server = 'smtp.gmail.com'
    smtp_port = 587
    provider = os.getenv("<enter your environment variable storing the email address>")
    emps = os.getenv('<enter the env variable storing the gmail app pasword>')
    if not provider or not emps:
        raise EnvironmentError("Missing email credentials in environment variables.")
    msg = MIMEMultipart()
    otp = random.randint(100000, 999999)
    otp_generated_time = time.time()

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
            a {{
                color: white;
            }}
            h5 {{
                color: #bfbfbf;
                font-style: none;
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

    msg['From'] = provider
    msg['To'] = usermail
    msg['Subject'] = "Your OTP for StockMind is here"
    msg['Reply-To'] = provider
    msg['X-Mailer'] = 'Python-Mail'
    msg.attach(MIMEText(btn, 'html'))

    try:
        s = smt.SMTP(smtp_server, smtp_port)
        s.starttls()
        s.login(provider, emps)
        s.sendmail(provider, usermail, msg.as_string())
    except smt.SMTPException as e:
        print(f"Failed to send email: {e}")
        raise
    finally:
        s.quit()

    return otp, otp_generated_time
def verifyOTP(otp: int, inp: int, otp_generated_time: float, expiry_seconds: int = 300) -> bool:
    otp = str(otp)
    inp = str(inp)
    current_time = time.time()

    if current_time - otp_generated_time > expiry_seconds:
        print("OTP expired.")
        return False

    if otp == inp:
        return True
    else:
        return False
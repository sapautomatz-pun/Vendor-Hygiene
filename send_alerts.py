#!/usr/bin/env python3
"""
send_alerts.py
Reads flagged_vendors.csv and sends an SMTP email per vendor.
Environment variables used:
  SMTP_HOST      - SMTP server hostname (required)
  SMTP_PORT      - SMTP port (optional, default 587)
  SMTP_USER      - SMTP username (required)
  SMTP_PASS      - SMTP password (required)
  FROM_EMAIL     - From email address (optional, defaults to SMTP_USER)
  DRY_RUN        - If "1" or "true" do not send emails, only print (optional)

Usage:
  python code/send_alerts.py --input flagged_vendors.csv --template templates/email_template.txt
"""
import csv
import os
import sys
import argparse
import smtplib
import time
from email.message import EmailMessage
from string import Template

DEFAULT_SMTP_PORT = 587
RETRY_COUNT = 3
RETRY_DELAY = 5  # seconds

def load_template(path):
    with open(path, 'r', encoding='utf-8') as f:
        return Template(f.read())

def send_email(smtp_host, smtp_port, smtp_user, smtp_pass, from_addr, to_addr, subject, body):
    msg = EmailMessage()
    msg['From'] = from_addr
    msg['To'] = to_addr
    msg['Subject'] = subject
    msg.set_content(body)

    for attempt in range(1, RETRY_COUNT + 1):
        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            return True
        except Exception as e:
            print(f"[WARN] Send failed attempt {attempt} for {to_addr}: {e}", file=sys.stderr)
            if attempt < RETRY_COUNT:
                time.sleep(RETRY_DELAY)
            else:
                print(f"[ERROR] Giving up on {to_addr}", file=sys.stderr)
                return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='flagged_vendors.csv', help='CSV with flagged vendors')
    parser.add_argument('--template', default='templates/email_template.txt', help='Email template file')
    parser.add_argument('--to-column', default='contact_email', help='CSV column with recipient email')
    parser.add_argument('--vendor-column', default='vendor', help='CSV column with vendor id/name')
    parser.add_argument('--dry-run', action='store_true', help='Do not actually send emails')
    args = parser.parse_args()

    smtp_host = os.getenv('SMTP_HOST')
    smtp_port = int(os.getenv('SMTP_PORT', DEFAULT_SMTP_PORT))
    smtp_user = os.getenv('SMTP_USER')
    smtp_pass = os.getenv('SMTP_PASS')
    from_email = os.getenv('FROM_EMAIL') or smtp_user
    dry_env = os.getenv('DRY_RUN', '').lower() in ('1', 'true', 'yes')

    dry_run = args.dry_run or dry_env

    if not smtp_host or not smtp_user or not smtp_pass:
        print("[ERROR] SMTP_HOST, SMTP_USER and SMTP_PASS must be set in environment", file=sys.stderr)
        if not dry_run:
            sys.exit(2)

    if not os.path.isfile(args.input):
        print(f"[ERROR] Input CSV not found: {args.input}", file=sys.stderr)
        sys.exit(2)

    if not os.path.isfile(args.template):
        print(f"[ERROR] Email template not found: {args.template}", file=sys.stderr)
        sys.exit(2)

    template = load_template(args.template)

    sent = 0
    failed = 0

    with open(args.input, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            to_addr = row.get(args.to_column) or row.get('email') or row.get('contact')
            vendor = row.get(args.vendor_column, 'Unknown Vendor')
            # Prepare template variables - extend as needed
            vars = {
                'vendor': vendor,
                'score': row.get('score', ''),
                'avg_delivery_lag': row.get('avg_delivery_lag', ''),
                'late_po_pct': row.get('late_po_pct', ''),
                'price_cv': row.get('price_cv', ''),
                'flag': row.get('flag', '')
            }
            subject = f"Action Required Vendor Performance {vendor} Flag {vars.get('flag')}"
            body = template.safe_substitute(vars)

            if not to_addr:
                print(f"[WARN] No recipient email for vendor {vendor}, skipping", file=sys.stderr)
                failed += 1
                continue

            print(f"[INFO] Preparing email to {to_addr} for {vendor}")
            if dry_run:
                print("--- DRY RUN ---")
                print("To:", to_addr)
                print("Subject:", subject)
                print(body)
                print("---------------")
                sent += 1
                continue

            ok = send_email(smtp_host, smtp_port, smtp_user, smtp_pass, from_email, to_addr, subject, body)
            if ok:
                sent += 1
            else:
                failed += 1

    print(f"[RESULT] Emails sent: {sent} failed: {failed}")
    if failed > 0:
        sys.exit(1)

if __name__ == '__main__':
    main()

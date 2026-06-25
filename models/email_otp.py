# -*- coding: utf-8 -*-

import random
import string
from datetime import datetime, timedelta
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class EmailOtp(models.Model):
    _name = 'email.otp'
    _description = 'Email OTP Verification'
    _rec_name = 'email_address'

    email_address = fields.Char(string='Email Address', required=True)
    otp_code = fields.Char(string='OTP Code', required=True)
    is_verified = fields.Boolean(string='Verified', default=False)
    expiry_time = fields.Datetime(string='Expiry Time', required=True)
    attempts = fields.Integer(string='Verification Attempts', default=0)
    max_attempts = fields.Integer(string='Max Attempts', default=3)
    created_date = fields.Datetime(string='Created Date', default=fields.Datetime.now)
    last_sent_time = fields.Datetime(string='Last Sent Time', default=fields.Datetime.now)
    resend_count = fields.Integer(string='Resend Count', default=0)
    max_resends = fields.Integer(string='Max Resends', default=3)
    cif_form_id = fields.Many2one('cif.form', string='Related CIF Form')
    field_type = fields.Selection([
        ('email', 'Email'),
        ('email_address', 'Alternate Email'),
        ('new_email_change', 'New Email in Change Mode')
    ], string='Field Type', required=True)

    @api.model
    def generate_otp(self, email_address, field_type, cif_form_id=None):
        """Generate a new OTP for the given email address"""
        # Generate 6-digit OTP
        otp_code = ''.join(random.choices(string.digits, k=6))

        # Set expiry time to 2 minutes from now
        expiry_time = datetime.now() + timedelta(minutes=2)

        # Delete any existing OTPs for this email address and field type
        existing_otps = self.search([
            ('email_address', '=', email_address),
            ('field_type', '=', field_type),
            ('cif_form_id', '=', cif_form_id)
        ])
        existing_otps.unlink()

        # Create new OTP record
        otp_record = self.create({
            'email_address': email_address,
            'otp_code': otp_code,
            'expiry_time': expiry_time,
            'field_type': field_type,
            'cif_form_id': cif_form_id,
        })

        return otp_record

    def verify_otp(self, entered_otp):
        """Verify the OTP code"""
        # Check if OTP has expired
        if datetime.now() > self.expiry_time:
            return {
                'success': False,
                'message': _('Verification code has expired. Please request a new one.')
            }

        # Check if maximum attempts exceeded
        if self.attempts >= self.max_attempts:
            return {
                'success': False,
                'message': _('Maximum verification attempts exceeded. Please request a new code.')
            }

        # Increment attempt counter
        self.attempts += 1

        # Check if OTP matches
        if self.otp_code == entered_otp:
            self.is_verified = True
            return {
                'success': True,
                'message': _('Email address verified successfully!')
            }
        else:
            remaining_attempts = self.max_attempts - self.attempts
            if remaining_attempts > 0:
                return {
                    'success': False,
                    'message': _('Invalid verification code. Please try again. Attempts remaining: %d') % remaining_attempts
                }
            else:
                return {
                    'success': False,
                    'message': _('Invalid verification code. Maximum attempts reached. Please request a new code.')
                }

    def can_resend_otp(self):
        """Check if OTP can be resent (60 second cooldown)"""
        if not self.last_sent_time:
            return True

        time_since_last_send = datetime.now() - self.last_sent_time
        cooldown_period = timedelta(seconds=60)

        return time_since_last_send >= cooldown_period

    def get_resend_cooldown_remaining(self):
        """Get remaining cooldown time in seconds"""
        if not self.last_sent_time:
            return 0

        time_since_last_send = datetime.now() - self.last_sent_time
        cooldown_period = timedelta(seconds=60)
        remaining = cooldown_period - time_since_last_send

        return max(0, int(remaining.total_seconds()))

    def resend_otp(self):
        """Resend OTP with cooldown check"""
        if not self.can_resend_otp():
            remaining_seconds = self.get_resend_cooldown_remaining()
            remaining_minutes = remaining_seconds // 60
            remaining_secs = remaining_seconds % 60
            return {
                'success': False,
                'message': _('Please wait %d:%02d before requesting a new code') % (remaining_minutes, remaining_secs),
                'cooldown_remaining': remaining_seconds
            }

        if self.resend_count >= self.max_resends:
            return {
                'success': False,
                'message': _('Maximum resend attempts exceeded. Please try again later.')
            }

        # Generate new OTP
        self.otp_code = ''.join(random.choices(string.digits, k=6))
        self.expiry_time = datetime.now() + timedelta(minutes=2)
        self.last_sent_time = datetime.now()
        self.resend_count += 1
        self.attempts = 0  # Reset verification attempts

        # Send new OTP
        result = self.send_otp_via_email()
        if result['success']:
            result['message'] = _('New verification code sent to %s') % self.email_address

        return result

    def send_otp_via_email(self):
        """Send OTP via Odoo email"""
        try:
            # Get the company for email configuration
            company = self.env.company

            # Prepare email content
            subject = "Email Verification Code - 7th Key"
            body_html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background-color: #1d194c; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">7th Key</h1>
                </div>
                <div style="padding: 30px; background-color: #f9f9f9;">
                    <h2 style="color: #1d194c;">Email Verification Code</h2>
                    <p>Hello,</p>
                    <p>Please use the following verification code to verify your email address:</p>
                    <div style="background-color: #1d194c; color: white; font-size: 32px; font-weight: bold; 
                                padding: 20px; text-align: center; margin: 20px 0; border-radius: 8px; 
                                letter-spacing: 5px;">
                        {self.otp_code}
                    </div>
                    <p style="margin-top: 20px;"><strong>Important:</strong></p>
                    <ul>
                        <li>This code will expire in <strong>2 minutes</strong></li>
                        <li>Do not share this code with anyone</li>
                        <li>Use this code only for email verification</li>
                    </ul>
                    <p>If you did not request this verification, please ignore this email.</p>
                    <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd;">
                        <p style="font-size: 12px; color: #666;">
                            This is an automated message from 7th Key Client Information Form.
                        </p>
                    </div>
                </div>
            </div>
            """

            # Create and send email
            mail_values = {
                'subject': subject,
                'body_html': body_html,
                'email_to': self.email_address,
                'email_from': company.email or 'noreply@7thkey.com',
                'auto_delete': True,
            }

            mail = self.env['mail.mail'].create(mail_values)
            mail.send()

            return {
                'success': True,
                'message': _('Verification code sent successfully to %s') % self.email_address
            }

        except Exception as e:
            return {
                'success': False,
                'message': _('Error sending verification email: %s') % str(e)
            }


    @api.model
    def cleanup_expired_otps(self):
        """Cleanup expired OTPs (to be called by cron job)"""
        expired_otps = self.search([('expiry_time', '<', datetime.now())])
        expired_otps.unlink()

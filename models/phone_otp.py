# -*- coding: utf-8 -*-

import random
import string
from datetime import datetime, timedelta
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from twilio.rest import Client
from twilio.base.exceptions import TwilioException


class PhoneOtp(models.Model):
    _name = 'phone.otp'
    _description = 'Phone OTP Verification'
    _rec_name = 'phone_number'

    phone_number = fields.Char(string='Phone Number', required=True)
    otp_code = fields.Char(string='OTP Code', required=True)
    is_verified = fields.Boolean(string='Verified', default=False)
    expiry_time = fields.Datetime(string='Expiry Time', required=True)
    attempts = fields.Integer(string='Verification Attempts', default=0)
    max_attempts = fields.Integer(string='Max Attempts', default=3)
    created_date = fields.Datetime(string='Created Date', default=fields.Datetime.now)
    cif_form_id = fields.Many2one('cif.form', string='Related CIF Form')
    field_type = fields.Selection([
        ('mobile', 'Mobile'),
        ('phone', 'Phone')
    ], string='Field Type', required=True)

    @api.model
    def generate_otp(self, phone_number, field_type, cif_form_id=None):
        """Generate a new OTP for the given phone number"""
        # Generate 6-digit OTP
        otp_code = ''.join(random.choices(string.digits, k=6))

        # Set expiry time to 2 minutes from now
        expiry_time = datetime.now() + timedelta(minutes=2)

        # Delete any existing OTPs for this phone number and field type
        existing_otps = self.search([
            ('phone_number', '=', phone_number),
            ('field_type', '=', field_type),
            ('cif_form_id', '=', cif_form_id)
        ])
        existing_otps.unlink()

        # Create new OTP record
        otp_record = self.create({
            'phone_number': phone_number,
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
                'message': _('Phone number verified successfully!')
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
        """Check if OTP can be resent (2 minute cooldown)"""
        if not self.last_sent_time:
            return True

        time_since_last_send = datetime.now() - self.last_sent_time
        cooldown_period = timedelta(minutes=2)

        return time_since_last_send >= cooldown_period

    def get_resend_cooldown_remaining(self):
        """Get remaining cooldown time in seconds"""
        if not self.last_sent_time:
            return 0

        time_since_last_send = datetime.now() - self.last_sent_time
        cooldown_period = timedelta(minutes=2)
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
        self.expiry_time = datetime.now() + timedelta(minutes=10)
        self.last_sent_time = datetime.now()
        self.resend_count += 1
        self.attempts = 0  # Reset verification attempts

        # Send new OTP
        result = self.send_otp_via_twilio()
        if result['success']:
            result['message'] = _('New verification code sent to %s') % self.phone_number

        return result

    def send_otp_via_twilio(self):
        """Send OTP via Twilio SMS"""
        # Get the first configured Twilio account
        twilio_account = self.env['twilio.account'].search([('state', '=', 'confirm')], limit=1)

        if not twilio_account:
            raise UserError(_("No configured Twilio account found. Please configure Twilio SMS first."))

        try:
            client = Client(twilio_account.account_sid, twilio_account.auth_token)
            message_body = f"Your verification code is: {self.otp_code}. This code will expire in 2 minutes."

            message = client.messages.create(
                body=message_body,
                from_=twilio_account.from_number,
                to=self.phone_number
            )

            if message.sid:
                return {
                    'success': True,
                    'message': _('OTP sent successfully to %s') % self.phone_number
                }
            else:
                return {
                    'success': False,
                    'message': _('Failed to send OTP to %s') % self.phone_number
                }

        except TwilioException as e:
            return {
                'success': False,
                'message': _('Twilio Error: %s') % str(e)
            }
        except Exception as e:
            return {
                'success': False,
                'message': _('Error sending OTP: %s') % str(e)
            }

    def verify_otp(self, entered_otp):
        """Verify the entered OTP"""
        self.attempts += 1

        # Check if maximum attempts exceeded
        if self.attempts > self.max_attempts:
            return {
                'success': False,
                'message': _('Maximum verification attempts exceeded. Please request a new OTP.')
            }

        # Check if OTP is expired
        if datetime.now() > self.expiry_time:
            return {
                'success': False,
                'message': _('OTP has expired. Please request a new OTP.')
            }

        # Check if OTP matches
        if self.otp_code != entered_otp:
            return {
                'success': False,
                'message': _('Invalid OTP. Please try again. Attempts remaining: %d') % (self.max_attempts - self.attempts)
            }

        # OTP is valid
        self.is_verified = True
        return {
            'success': True,
            'message': _('Phone number verified successfully!')
        }

    @api.model
    def cleanup_expired_otps(self):
        """Cleanup expired OTPs (to be called by cron job)"""
        expired_otps = self.search([('expiry_time', '<', datetime.now())])
        expired_otps.unlink()

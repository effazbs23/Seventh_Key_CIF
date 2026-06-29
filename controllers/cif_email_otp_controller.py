# -*- coding: utf-8 -*-

import json
import re
from odoo import http, fields
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class CifEmailOtpController(http.Controller):

    def _is_valid_email(self, email):
        """Validate email format using regex"""
        email_regex = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
        return re.match(email_regex, email) is not None

    def _get_cif_request_session_for_token(self, token):
        CIFRequestSession = request.env['cif.request.session'].sudo()
        return CIFRequestSession.search([('cif_token', '=', token)], limit=1) or False

    def _cif_request_key(self, cif_request_session):
        # Key used inside request.session (HTTP session storage)
        return f"cif_session_{cif_request_session.id}"

    @http.route('/cif/send_email_otp', type='http', auth='public', methods=['POST'], csrf=False)
    def send_email_otp(self, **kwargs):
        """Send OTP to email address"""
        try:
            email_address = kwargs.get('email_address')
            field_type = kwargs.get('field_type')  # 'email' or 'email_address'
            token = kwargs.get('token')

            if not all([email_address, field_type, token]):
                return json.dumps({
                    'success': False,
                    'message': 'Missing required parameters'
                })

            # Validate email format
            if not self._is_valid_email(email_address):
                return json.dumps({
                    'success': False,
                    'message': 'Please enter a valid email address format (e.g., user@example.com)'
                })

            cif_request_session = self._get_cif_request_session_for_token(token)
            if not cif_request_session:
                return json.dumps({
                    'success': False,
                    'message': 'Invalid or expired token'
                })

            cif_request_key = self._cif_request_key(cif_request_session)

            try:
                cif_request_session._check_active_and_quota()
            except Exception:
                return json.dumps({
                    'success': False,
                    'message': 'Invalid or expired token'
                })

            # Generate and send OTP
            otp_record = request.env['email.otp'].sudo().generate_otp(
                email_address=email_address,
                field_type=field_type,
                cif_form_id=None  # For web form, no CIF record exists yet
            )

            # Send OTP via email
            result = otp_record.send_otp_via_email()

            # Store the OTP record ID in session for later verification
            cif_email_otp_record_key = f'email_otp_record_{field_type}_{cif_request_key}'
            request.session[cif_email_otp_record_key] = otp_record.id

            return json.dumps(result)

        except Exception as e:
            _logger.error(f"Error sending email OTP: {str(e)}")
            return json.dumps({
                'success': False,
                'message': f'Error sending verification email: {str(e)}'
            })

    @http.route('/cif/verify_email_otp', type='http', auth='public', methods=['POST'], csrf=False)
    def verify_email_otp(self, **kwargs):
        """Verify email OTP code"""
        try:
            otp_code = kwargs.get('otp_code')
            field_type = kwargs.get('field_type')  # 'email' or 'email_address'
            token = kwargs.get('token')

            if not all([otp_code, field_type, token]):
                return json.dumps({
                    'success': False,
                    'message': 'Missing required parameters'
                })

            cif_request_session = self._get_cif_request_session_for_token(token)
            if not cif_request_session:
                return json.dumps({
                    'success': False,
                    'message': 'Invalid or expired token'
                })

            cif_request_key = self._cif_request_key(cif_request_session)

            # Get the OTP record ID from request.session
            cif_email_otp_record_key = f'email_otp_record_{field_type}_{cif_request_key}'
            otp_record_id = request.session.get(cif_email_otp_record_key)

            if not otp_record_id:
                return json.dumps({
                    'success': False,
                    'message': 'No verification code found. Please request a new code.'
                })

            # Find the OTP record
            otp_record = request.env['email.otp'].sudo().browse(otp_record_id)

            if not otp_record.exists():
                return json.dumps({
                    'success': False,
                    'message': 'Verification code not found. Please request a new code.'
                })

            # Verify the OTP
            result = otp_record.verify_otp(otp_code)

            if result['success']:
                verification_key = f'email_verified_{field_type}_{cif_request_key}'
                email_address_key = f'email_verified_{field_type}_address_{cif_request_key}'
                request.session[verification_key] = True
                request.session[email_address_key] = otp_record.email_address
                # Clean up the OTP record
                otp_record.unlink()
                # Remove the OTP record ID from session
                if cif_email_otp_record_key in request.session:
                    del request.session[cif_email_otp_record_key]

            return json.dumps(result)

        except Exception as e:
            _logger.error(f"Error verifying email OTP: {str(e)}")
            return json.dumps({
                'success': False,
                'message': f'Error verifying email: {str(e)}'
            })

    @http.route('/cif/check_email_verification_status', type='http', auth='public', methods=['POST'], csrf=False)
    def check_email_verification_status(self, **kwargs):
        """Check if email address is verified"""
        try:
            field_type = kwargs.get('field_type')  # 'email' or 'email_address'
            token = kwargs.get('token')
            current_email = kwargs.get('current_email', '')  # Current email in the field

            if not all([field_type, token]):
                return json.dumps({
                    'success': False,
                    'verified': False
                })

            cif_request_session = self._get_cif_request_session_for_token(token)
            if not cif_request_session:
                return json.dumps({
                    'success': True,
                    'verified': False
                })

            cif_request_key = self._cif_request_key(cif_request_session)

            # Check verification status in session
            verification_key = f'email_verified_{field_type}_{cif_request_key}'
            email_address_key = f'email_verified_{field_type}_address_{cif_request_key}'
            is_verified = request.session.get(verification_key, False)
            verified_email = request.session.get(email_address_key, '')

            # Only show as verified if the current email matches the verified email
            is_current_verified = is_verified and (current_email == verified_email) and current_email.strip()

            return json.dumps({
                'success': True,
                'verified': is_current_verified
            })

        except Exception as e:
            _logger.error(f"Error checking email verification status: {str(e)}")
            return json.dumps({
                'success': False,
                'verified': False
            })

    @http.route('/cif/resend_email_otp', type='http', auth='public', methods=['POST'], csrf=False)
    def resend_email_otp(self, **kwargs):
        """Resend email OTP with cooldown check"""
        try:
            field_type = kwargs.get('field_type')  # 'email' or 'email_address'
            token = kwargs.get('token')

            if not all([field_type, token]):
                return json.dumps({
                    'success': False,
                    'message': 'Missing required parameters'
                })

            cif_request_session = self._get_cif_request_session_for_token(token)
            if not cif_request_session:
                return json.dumps({
                    'success': False,
                    'message': 'Invalid or expired token'
                })

            cif_request_key = self._cif_request_key(cif_request_session)

            cif_email_otp_record_key = f'email_otp_record_{field_type}_{cif_request_key}'
            otp_record_id = request.session.get(cif_email_otp_record_key)

            if not otp_record_id:
                return json.dumps({
                    'success': False,
                    'message': 'No verification session found. Please start verification again.'
                })

            # Find the OTP record
            otp_record = request.env['email.otp'].sudo().browse(otp_record_id)

            if not otp_record.exists():
                return json.dumps({
                    'success': False,
                    'message': 'Verification code not found. Please start verification again.'
                })

            # Resend the OTP
            result = otp_record.resend_otp()

            return json.dumps(result)

        except Exception as e:
            _logger.error(f"Error resending email OTP: {str(e)}")
            return json.dumps({
                'success': False,
                'message': f'Error resending verification email: {str(e)}'
            })

    # =========================================================
    # ==   Unified Email OTP Routes for Change CIF Mode ==
    # =========================================================

    def _get_change_request_for_token(self, token):
        """Get change request for the given token"""
        CIFChangeRequest = request.env['cif.change.request'].sudo()
        return CIFChangeRequest.search([('token', '=', token)], limit=1) or False

    @http.route([
        '/cif/change/send-new-email-otp',
        '/client-information-form/change/send-new-email-otp'
    ], type='jsonrpc', auth='public', methods=['POST'], csrf=False)
    def change_cif_send_new_email_otp(self, **post):
        """
        Unified route to send OTP to new email address in Change CIF mode.
        Uses the email.otp model for DRY principle - same as new CIF.
        """
        try:
            token = post.get('token')
            new_email = post.get('new_email', '').strip().lower()

            if not token or not new_email:
                return {'success': False, 'message': 'Token and new email are required.'}

            # Validate email format
            if not self._is_valid_email(new_email):
                return {'success': False, 'message': 'Please enter a valid email address format.'}

            # Get change request
            change_req = self._get_change_request_for_token(token)
            if not change_req:
                return {'success': False, 'message': 'Invalid or expired change request.'}

            # Check if change request is not expired
            try:
                change_req._check_not_expired()
            except Exception as e:
                return {'success': False, 'message': str(e) or 'This link has expired.'}

            # Store the new email in change request
            change_req.write({'new_email': new_email})

            # Use unified email.otp model for OTP generation (DRY principle)
            try:
                otp_record = request.env['email.otp'].sudo().generate_otp(
                    email_address=new_email,
                    field_type='new_email_change',  # Special type for change mode new email
                    cif_form_id=None  # No CIF form for change requests
                )

                # Send OTP via email
                result = otp_record.send_otp_via_email()

                if result['success']:
                    # Store OTP record ID in session for later verification
                    change_otp_key = f'change_email_otp_record_{token}'
                    request.session[change_otp_key] = otp_record.id

                    return {
                        'success': True,
                        'message': f'Verification code sent to {new_email}. Please check your inbox.'
                    }
                else:
                    return {'success': False, 'message': result.get('message', 'Failed to send verification email.')}

            except Exception as e:
                _logger.error(f"Failed to send new email OTP in change mode: {e}")
                return {'success': False, 'message': 'Failed to send verification email. Please try again.'}

        except Exception as e:
            _logger.exception(f"Error in change_cif_send_new_email_otp: {e}")
            return {'success': False, 'message': 'An unexpected error occurred.'}

    @http.route([
        '/cif/change/verify-new-email-otp',
        '/client-information-form/change/verify-new-email-otp'
    ], type='jsonrpc', auth='public', methods=['POST'], csrf=False)
    def change_cif_verify_new_email_otp(self, **post):
        """
        Unified route to verify OTP for new email address in Change CIF mode.
        Uses the email.otp model for DRY principle - same as new CIF.
        """
        try:
            token = post.get('token')
            otp_code = post.get('otp_code', '').strip()

            if not token or not otp_code:
                return {'success': False, 'message': 'Token and OTP code are required.'}

            # Get change request
            change_req = self._get_change_request_for_token(token)
            if not change_req:
                return {'success': False, 'message': 'Invalid or expired change request.'}

            # Check if change request is not expired
            try:
                change_req._check_not_expired()
            except Exception as e:
                return {'success': False, 'message': str(e) or 'This link has expired.'}

            # Get OTP record from session
            change_otp_key = f'change_email_otp_record_{token}'
            otp_record_id = request.session.get(change_otp_key)

            if not otp_record_id:
                return {'success': False, 'message': 'No verification code found. Please request a new code.'}

            # Find the OTP record
            otp_record = request.env['email.otp'].sudo().browse(otp_record_id)

            if not otp_record.exists():
                return {'success': False, 'message': 'Verification code not found. Please request a new code.'}

            # Verify the OTP using unified email.otp model
            result = otp_record.verify_otp(otp_code)

            if result['success']:
                # Mark new email as verified in change request
                change_req.write({
                    'is_new_email_verified': True,
                    'new_email_verified_at': fields.Datetime.now(),
                })

                # Clean up
                otp_record.unlink()
                if change_otp_key in request.session:
                    del request.session[change_otp_key]

                return {
                    'success': True,
                    'message': 'Email address verified successfully!'
                }
            else:
                return result

        except Exception as e:
            _logger.exception(f"Error in change_cif_verify_new_email_otp: {e}")
            return {'success': False, 'message': 'An unexpected error occurred during verification.'}

    @http.route([
        '/cif/change/resend-new-email-otp',
        '/client-information-form/change/resend-new-email-otp'
    ], type='jsonrpc', auth='public', methods=['POST'], csrf=False)
    def change_cif_resend_new_email_otp(self, **post):
        """
        Unified route to resend OTP for new email address in Change CIF mode.
        Uses the email.otp model for DRY principle - same as new CIF.
        """
        try:
            token = post.get('token')

            if not token:
                return {'success': False, 'message': 'Token is required.'}

            # Get change request
            change_req = self._get_change_request_for_token(token)
            if not change_req:
                return {'success': False, 'message': 'Invalid or expired change request.'}

            # Check if change request is not expired
            try:
                change_req._check_not_expired()
            except Exception as e:
                return {'success': False, 'message': str(e) or 'This link has expired.'}

            # Get OTP record from session
            change_otp_key = f'change_email_otp_record_{token}'
            otp_record_id = request.session.get(change_otp_key)

            if not otp_record_id:
                return {'success': False, 'message': 'No verification session found. Please start verification again.'}

            # Find the OTP record
            otp_record = request.env['email.otp'].sudo().browse(otp_record_id)

            if not otp_record.exists():
                return {'success': False, 'message': 'Verification code not found. Please start verification again.'}

            # Resend the OTP using unified email.otp model
            result = otp_record.resend_otp()

            return result

        except Exception as e:
            _logger.exception(f"Error in change_cif_resend_new_email_otp: {e}")
            return {'success': False, 'message': 'An unexpected error occurred while resending code.'}


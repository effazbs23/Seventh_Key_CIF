# -*- coding: utf-8 -*-

import json
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class CifOtpController(http.Controller):

    def _get_cif_request_session_for_token(self, token):
        CIFRequestSession = request.env['cif.request.session'].sudo()
        return CIFRequestSession.search([('cif_token', '=', token)], limit=1) or False

    def _cif_request_key(self, cif_request_session):
        # Key used inside request.session (HTTP session storage)
        return f"cif_session_{cif_request_session.id}"

    @http.route('/cif/send_otp', type='http', auth='public', methods=['POST'], csrf=False)
    def send_otp(self, **kwargs):
        """Send OTP to phone number"""
        try:
            phone_number = kwargs.get('phone_number')
            field_type = kwargs.get('field_type')  # 'mobile' or 'phone'
            token = kwargs.get('token')

            if not all([phone_number, field_type, token]):
                return json.dumps({'success': False, 'message': 'Missing required parameters'})

            cif_request_session = self._get_cif_request_session_for_token(token)
            if not cif_request_session:
                return json.dumps({'success': False, 'message': 'Invalid or expired token'})

            cif_request_key = self._cif_request_key(cif_request_session)

            try:
                cif_request_session._check_active_and_quota()
            except Exception:
                return json.dumps({'success': False, 'message': 'Invalid or expired token'})

            # Generate and send OTP
            otp_record = request.env['phone.otp'].sudo().generate_otp(
                phone_number=phone_number,
                field_type=field_type,
                cif_form_id=None
            )

            result = otp_record.send_otp_via_twilio()

            cif_otp_record_key = f'otp_record_{field_type}_{cif_request_key}'
            request.session[cif_otp_record_key] = otp_record.id

            return json.dumps(result)

        except Exception as e:
            _logger.error(f"Error sending OTP: {str(e)}")
            return json.dumps({'success': False, 'message': f'Error sending OTP: {str(e)}'})

    @http.route('/cif/verify_otp', type='http', auth='public', methods=['POST'], csrf=False)
    def verify_otp(self, **kwargs):
        """Verify OTP code"""
        try:
            otp_code = kwargs.get('otp_code')
            field_type = kwargs.get('field_type')  # 'mobile' or 'phone'
            token = kwargs.get('token')

            if not all([otp_code, field_type, token]):
                return json.dumps({'success': False, 'message': 'Missing required parameters'})

            cif_request_session = self._get_cif_request_session_for_token(token)
            if not cif_request_session:
                return json.dumps({'success': False, 'message': 'Invalid or expired token'})

            cif_request_key = self._cif_request_key(cif_request_session)
            cif_otp_record_key = f'otp_record_{field_type}_{cif_request_key}'
            otp_record_id = request.session.get(cif_otp_record_key)

            if not otp_record_id:
                return json.dumps({'success': False, 'message': 'No OTP found. Please request a new OTP.'})

            otp_record = request.env['phone.otp'].sudo().browse(otp_record_id)
            if not otp_record.exists():
                return json.dumps({'success': False, 'message': 'OTP record not found. Please request a new OTP.'})

            result = otp_record.verify_otp(otp_code)

            if result.get('success'):
                verification_key = f'verified_{field_type}_{cif_request_key}'
                phone_number_key = f'verified_{field_type}_number_{cif_request_key}'
                request.session[verification_key] = True
                request.session[phone_number_key] = otp_record.phone_number
                otp_record.unlink()
                if cif_otp_record_key in request.session:
                    del request.session[cif_otp_record_key]

            return json.dumps(result)

        except Exception as e:
            _logger.error(f"Error verifying OTP: {str(e)}")
            return json.dumps({'success': False, 'message': f'Error verifying OTP: {str(e)}'})

    @http.route('/cif/check_verification_status', type='http', auth='public', methods=['POST'], csrf=False)
    def check_verification_status(self, **kwargs):
        """Check if phone number is verified"""
        try:
            field_type = kwargs.get('field_type')
            token = kwargs.get('token')
            current_number = kwargs.get('current_number', '')

            if not all([field_type, token]):
                return json.dumps({'success': False, 'verified': False})

            cif_request_session = self._get_cif_request_session_for_token(token)
            if not cif_request_session:
                return json.dumps({'success': True, 'verified': False})

            cif_request_key = self._cif_request_key(cif_request_session)

            verification_key = f'verified_{field_type}_{cif_request_key}'
            phone_number_key = f'verified_{field_type}_number_{cif_request_key}'
            is_verified = request.session.get(verification_key, False)
            verified_number = request.session.get(phone_number_key, '')

            is_current_verified = is_verified and (current_number == verified_number) and current_number.strip()
            return json.dumps({'success': True, 'verified': is_current_verified})

        except Exception as e:
            _logger.error(f"Error checking verification status: {str(e)}")
            return json.dumps({'success': False, 'verified': False})

    @http.route('/cif/resend_otp', type='http', auth='public', methods=['POST'], csrf=False)
    def resend_otp(self, **kwargs):
        """Resend OTP to phone number with cooldown check"""
        try:
            field_type = kwargs.get('field_type')
            token = kwargs.get('token')

            if not all([field_type, token]):
                return json.dumps({'success': False, 'message': 'Missing required parameters'})

            cif_request_session = self._get_cif_request_session_for_token(token)
            if not cif_request_session:
                return json.dumps({'success': False, 'message': 'Invalid or expired token'})

            cif_request_key = self._cif_request_key(cif_request_session)

            cif_otp_record_key = f'otp_record_{field_type}_{cif_request_key}'
            otp_record_id = request.session.get(cif_otp_record_key)

            if not otp_record_id:
                return json.dumps({'success': False, 'message': 'No OTP session found. Please start verification again.'})

            otp_record = request.env['phone.otp'].sudo().browse(otp_record_id)
            if not otp_record.exists():
                return json.dumps({'success': False, 'message': 'OTP record not found. Please start verification again.'})

            result = otp_record.resend_otp()
            return json.dumps(result)

        except Exception as e:
            _logger.error(f"Error resending OTP: {str(e)}")
            return json.dumps({'success': False, 'message': f'Error resending OTP: {str(e)}'})

# -*- coding: utf-8 -*-

from odoo import fields, http, _
from odoo.http import request
from odoo.exceptions import ValidationError
import logging
import base64
from ..models.utils import PAYMENT_TYPE_OPTIONS

_logger = logging.getLogger(__name__)


class CIFController(http.Controller):
    """
    This controller manages the separate workflows for Individual and Company CIF forms.
    It uses distinct routes for each workflow to ensure clarity and maintainability.
    """

    # --- PRIVATE HELPER METHODS ---

    def _sanitize_email(self, email):
        return (email or '').strip().lower() or False


    def _format_datetime_for_user(self, utc_datetime):
        """Convert UTC datetime to user's timezone and format for display"""
        if not utc_datetime:
            return ''

        # Get the user's timezone from context or use browser timezone
        tz_name = request.env.context.get('tz') or request.env.user.tz or 'UTC'

        try:
            from datetime import datetime
            import pytz

            # Ensure the datetime is timezone-aware (UTC)
            if isinstance(utc_datetime, str):
                utc_datetime = fields.Datetime.from_string(utc_datetime)

            # Localize to UTC if naive
            utc_tz = pytz.UTC
            if utc_datetime.tzinfo is None:
                utc_datetime = utc_tz.localize(utc_datetime)

            # Convert to user's timezone
            user_tz = pytz.timezone(tz_name)
            local_datetime = utc_datetime.astimezone(user_tz)

            # Format: YYYY-MM-DD HH:MM:SS (Timezone)
            return local_datetime.strftime('%Y-%m-%d %H:%M:%S %Z')
        except Exception as e:
            _logger.warning(f"Failed to convert datetime to user timezone: {e}")
            # Fallback to original datetime string
            return str(utc_datetime)

    def _find_or_create_partner(self, partner_vals, email):
        """Find or create a partner based on email.

        We *avoid* creating duplicates by reusing an existing partner when email matches.
        """
        email_norm = self._sanitize_email(email)
        Partner = request.env['res.partner'].sudo()
        if email_norm:
            existing = Partner.search([('email', '=', email_norm)], limit=1)
            if existing:
                # Update basic fields if they are empty; do not overwrite good data.
                safe_vals = dict(partner_vals or {})
                safe_vals['email'] = email_norm
                update_vals = {}
                for k, v in safe_vals.items():
                    if k == 'email':
                        continue
                    if v and not getattr(existing, k, False):
                        update_vals[k] = v
                if update_vals:
                    existing.write(update_vals)
                return existing

        if partner_vals is None:
            partner_vals = {}
        if email_norm:
            partner_vals = dict(partner_vals)
            partner_vals['email'] = email_norm
        return Partner.create(partner_vals)

    def _get_allowed_cif_submissions(self, sale_order):
        return 1

    def _get_cif_submissions_done(self, sale_order):
        return 1 if sale_order.cif_form_id else 0

    def _get_render_values(self, sale_order):
        """Helper to fetch common data needed for rendering any form template."""
        order_line = sale_order.order_line and sale_order.order_line[0] or None
        
        # Prepare security questions with all necessary fields
        security_questions = request.env['security.question'].sudo().search([])
        security_questions_data = [{
            'id': q.id,
            'question': q.question,
            'ans_max_length': q.ans_max_length or 255
        } for q in security_questions]
        
        return {
            'sale_order': sale_order,
            'date': fields.Date.today(),
            'titles': request.env['res.partner.title'].sudo().search([]),
            'countries': request.env['res.country'].sudo().search([]),
            'payment_plans': request.env['installment.option'].sudo().search([]),
            'unit_no': order_line[0].product_id.name if order_line else '',
            # 'payment_methods': request.env['account.payment.method.line'].sudo().search([
            #     ('payment_method_id.payment_type', '=', 'inbound')
            # ]),
            'payment_type_options': PAYMENT_TYPE_OPTIONS,
            'security_questions': security_questions_data,
            'agent_code': sale_order.agent_code or '',
            'agency_name': sale_order.agent_id.name if sale_order.agent_id else '',
            'agent_name': sale_order.agent_id.representative.name if sale_order.agent_id.representative else '',
            'agent_mobile': sale_order.agent_id.mobile if sale_order.agent_id else '',
            'agent_email': sale_order.agent_id.email if sale_order.agent_id else '',
            'agent_trade_license_no': sale_order.agent_id.trade_license_no if sale_order.agent_id else '',
            'max_share_percentage': 100.0,
        }

    def _get_cif_request_session_for_token(self, token):
        """Resolve a CIF request-session record (`cif.request.session`) for a given public token.

        Naming note:
        - We avoid 'session' alone to prevent confusion with `request.session` (the HTTP server session).

        Returns (cif_request_session, sale_order) or (False, False).
        """
        if not token:
            return (False, False)

        CIFRequestSession = request.env['cif.request.session'].sudo()
        cif_request_session = CIFRequestSession.search([('cif_token', '=', token)], limit=1)
        if cif_request_session:
            return (cif_request_session, cif_request_session.sale_order_id)

        return (False, False)

    def _get_cif_request_key(self, cif_request_session):
        """Return a stable key prefix for values stored in `request.session`.

        We key by CIF request-session id to prevent OTP/verification state leaking across different
        CIF requests.
        """
        return f"cif_session_{cif_request_session.id}" if cif_request_session and cif_request_session.id else False

    def _check_submission_capacity(self, cif_request_session):
        """Check if the session has remaining submission capacity.

        Returns True if capacity available, False otherwise.
        """
        if not cif_request_session:
            return False
        return len(cif_request_session.cif_form_ids) < cif_request_session.allowed_submissions

    def _mask_email(self, email):
        """Mask email address for identity verification.

        Example: john.doe@example.com → j*****e@example.com
        """
        if not email or '@' not in email:
            return '***@***.***'

        local, domain = email.split('@', 1)

        if len(local) <= 2:
            masked_local = local[0] + '*'
        else:
            masked_local = local[0] + ('*' * (len(local) - 2)) + local[-1]

        return f"{masked_local}@{domain}"

    # =========================================================
    # ==          INDIVIDUAL CLIENT FORM WORKFLOW            ==
    # =========================================================

    @http.route('/client-information-form/individual', type='http', auth='public', website=True)
    def render_individual_cif_form(self, token=None, **kw):
        """Displays the web form for INDIVIDUAL clients."""
        if not token:
            _logger.warning("Individual CIF form accessed without a token.")
            return request.render('website.404')

        cif_request_session, sale_order = self._get_cif_request_session_for_token(token)
        if not cif_request_session or not sale_order:
            _logger.debug('render_individual_cif_form: CIF request token not found token=%s', token)
            return request.render('bs_cif_process.cif_form_already_submitted_template')

        try:
            cif_request_session._check_active_and_quota()
        except Exception:
            _logger.debug(
                'render_individual_cif_form: CIF request token expired token=%s cif_request_session=%s',
                token,
                cif_request_session.id,
            )
            return request.render('bs_cif_process.cif_form_already_submitted_template')

        render_values = self._get_render_values(sale_order)
        render_values.update({'cif_request_session': cif_request_session})
        return request.render('bs_cif_process.cif_form_template', render_values)

    @http.route('/cif/submit/individual/<string:model_name>', type='http', auth='public', methods=['POST'], website=True, csrf=True)
    def submit_individual_cif_form(self, model_name, **post):
        """Handles the submission for an INDIVIDUAL client, supports draw+upload signature."""
        access_token = post.get('cif_token')

        cif_request_session, sale_order = self._get_cif_request_session_for_token(access_token)
        if not cif_request_session or not sale_order:
            _logger.debug('submit_individual_cif_form: CIF request token not found access_token=%s', access_token)
            return request.render('bs_cif_process.cif_form_already_submitted_template')

        try:
            cif_request_session._check_active_and_quota()
        except Exception:
            return request.render('bs_cif_process.cif_form_already_submitted_template')

        cif_request_key = self._get_cif_request_key(cif_request_session)

        try:
            with request.env.cr.savepoint():
                # Process file uploads for supporting documents
                passport_doc_ids = []
                emirates_doc_ids = []

                # Handle passport supporting documents
                passport_files = request.httprequest.files.getlist('passport_docs')
                for passport_file in passport_files:
                    if passport_file and getattr(passport_file, 'filename', None):
                        content = passport_file.read()
                        if content:
                            attachment = request.env['ir.attachment'].sudo().create({
                                'name': passport_file.filename,
                                'type': 'binary',
                                'datas': base64.b64encode(content),
                                'mimetype': passport_file.content_type or 'application/octet-stream',
                            })
                            passport_doc_ids.append(attachment.id)

                # Handle emirates ID supporting documents
                emirates_files = request.httprequest.files.getlist('emirates_id_docs')
                for emirates_file in emirates_files:
                    if emirates_file and getattr(emirates_file, 'filename', None):
                        content = emirates_file.read()
                        if content:
                            attachment = request.env['ir.attachment'].sudo().create({
                                'name': emirates_file.filename,
                                'type': 'binary',
                                'datas': base64.b64encode(content),
                                'mimetype': emirates_file.content_type or 'application/octet-stream',
                            })
                            emirates_doc_ids.append(attachment.id)

                # Prepare contact data from the form
                partner_vals = {
                    'name': f"{post.get('first_name', '')} {post.get('middle_name') or ''} {post.get('last_name', '')}".strip().replace(
                        '  ', ' '),
                    'middle_name': post.get('middle_name', ''),
                    'company_type': 'person',
                    'email': post.get('email'),
                    'mobile': post.get('mobile'),
                    'phone': post.get('phone'),
                    'email_address': post.get('email_address'),
                    'street': post.get('street_name'),
                    'street2': f"Unit/Villa: {post.get('unit_villa_no', '')}, Building: {post.get('building_name', '')}",
                    'city': post.get('city'), 'zip': post.get('postal_code'),
                    'passport_no': post.get('passport_no'),
                    'passport_supporting_docs': [(6, 0, passport_doc_ids)] if passport_doc_ids else [],
                    'national_id_no': post.get('emirates_no'),
                    'supporting_document_ids': [(6, 0, emirates_doc_ids)] if emirates_doc_ids else [],
                    'date_of_birth': post.get('date_of_birth') or False,
                    'gender': post.get('gender'),
                    'nationality': int(post.get('nationality_id')) if post.get('nationality_id') else False,
                    'country_id': int(post.get('country_id')) if post.get('country_id') else False,
                    'payment_type': post.get('payment_type') or False,
                    'source_of_income': post.get('source_of_income'),
                    'residency_status': post.get('uae_residency_status'),
                }

                # Handle signature: file or base64 hidden input
                signature_b64 = None
                signature_file = request.httprequest.files.get('signature') or \
                                 request.httprequest.files.get('signature[0][0]')
                if signature_file and getattr(signature_file, 'filename', None):
                    content = signature_file.read()
                    if content:
                        signature_b64 = base64.b64encode(content)
                if not signature_b64:
                    raw_b64 = post.get('signature_data')
                    if raw_b64:
                        if raw_b64.startswith('data:'):
                            try:
                                raw_b64 = raw_b64.split(',', 1)[1]
                            except Exception:
                                raw_b64 = ''
                        try:
                            base64.b64decode(raw_b64)
                            signature_b64 = raw_b64.encode()
                        except Exception:
                            signature_b64 = None

                if not signature_b64:
                    return request.render('bs_cif_process.cif_form_error_template', {
                        'error_message': 'Signature is required. Please go back and draw or upload your signature.',
                        'sale_order_name': sale_order.name,
                    })

                partner_vals['signature'] = signature_b64

                partner = sale_order.partner_id
                partner.write(partner_vals)

                # Create security question answers for partner
                security_answers = []
                for i in range(1, 4):
                    question_id = post.get(f'security_question_{i}')
                    answer = post.get(f'security_answer_{i}', '').strip()
                    if question_id and answer:
                        security_answers.append((0, 0, {
                            'sequence': i,
                            'question_id': int(question_id),
                            'answer': answer,
                        }))
                
                if security_answers:
                    partner.write({'security_answer_ids': [(5, 0, 0)] + security_answers})

                # ✅ Check capacity BEFORE creating CIF form
                if not self._check_submission_capacity(cif_request_session):
                    return request.render('bs_cif_process.cif_form_already_submitted_template')

                cif_vals = {k: v for k, v in post.items() if hasattr(request.env['cif.form'], k)}
                cif_vals.update({
                    'source_sale_order_id': sale_order.id, 'client_type': 'person',
                    'created_partner_id': partner.id, 'signature': signature_b64,
                    'agent_id': sale_order.agent_id.id if sale_order.agent_id else False,
                    'passport_supporting_docs': [(6, 0, passport_doc_ids)] if passport_doc_ids else [],
                    'supporting_document_ids': [(6, 0, emirates_doc_ids)] if emirates_doc_ids else [],
                    'cif_request_session_id': cif_request_session.id if cif_request_session else False,
                    'residency_status': post.get('uae_residency_status'),
                    'national_id_no': post.get('emirates_no'),
                    # Add verification status from session
                    'is_mobile_verified': request.session.get(f'verified_mobile_{cif_request_key}', False),
                    'is_phone_verified': request.session.get(f'verified_phone_{cif_request_key}', False),
                    'is_email_verified': request.session.get(f'email_verified_email_{cif_request_key}', False),
                })

                if security_answers:
                    cif_vals['security_answer_ids'] = security_answers
                
                cif_record = request.env['cif.form'].sudo().create(cif_vals)

                # Link CIF record to Sale Order directly
                sale_order.sudo().write({'cif_form_id': cif_record.id})

                chatter_message = f"Client Information Form {cif_record.cif_no} submitted for: {partner.name}."
                # self._post_process_submission(sale_order, cif_record, chatter_message)
                sale_order.sudo().message_post(
                    body=chatter_message,
                )

                # Send notification to salesperson
                if sale_order.user_id:
                    template = request.env.ref('bs_cif_process.email_template_cif_submitted', raise_if_not_found=False)
                    if template:
                        template.sudo().with_context(
                            cif_form_id=cif_record.id,
                            cif_form_name=cif_record.cif_no,
                        ).send_mail(sale_order.id, force_send=True)
                    
                    # Send in-app notification to salesperson's Odoo notification inbox
                    # sale_order.user_id.partner_id.message_notify(
                    #     body=f"CIF Form {cif_record.cif_no} has been submitted for sale order {sale_order.name}.",
                    #     subtype="mail.mt_note",
                    #     message_type="user_notification",
                    #     subject="CIF Form Submitted",
                    # )

                # Consume CIF request quota atomically AFTER successful submission is persisted
                if cif_request_session:
                    cif_request_session.consume_submission_slot()
        except Exception as e:
            _logger.exception(f"Error during Individual CIF submission for SO {sale_order.name}: {e}")
            error_msg = e.args[0] if e.args else 'An unexpected error occurred during form submission.'
            return request.render('bs_cif_process.cif_form_error_template', {
                'error_message': error_msg,
                'sale_order_name': sale_order.name,
            })

        # Render thank you page instead of JSON response
        return request.render('bs_cif_process.cif_individual_thank_you_template', {
            'sale_order_name': sale_order.name,
        })

    # =========================================================
    # ==           COMPANY CLIENT FORM WORKFLOW              ==
    # =========================================================

    @http.route('/client-information-form/company', type='http', auth='public', website=True)
    def render_company_cif_form(self, token=None, **kw):
        """Displays the dedicated web form for COMPANY clients."""
        if not token:
            _logger.warning("Company CIF form accessed without a token.")
            return request.render('website.404')

        cif_request_session, sale_order = self._get_cif_request_session_for_token(token)
        if not cif_request_session or not sale_order:
            _logger.debug('render_company_cif_form: CIF request token not found token=%s', token)
            return request.render('bs_cif_process.cif_form_already_submitted_template')

        try:
            cif_request_session._check_active_and_quota()
        except Exception:
            _logger.debug(
                'render_company_cif_form: CIF request token expired token=%s cif_request_session=%s',
                token,
                cif_request_session.id,
            )
            return request.render('bs_cif_process.cif_form_already_submitted_template')

        render_values = self._get_render_values(sale_order)
        render_values.update({'cif_request_session': cif_request_session})
        return request.render('bs_cif_process.cif_company_form_template', render_values)

    @http.route('/cif/submit/company/<string:model_name>', type='http', auth='public', methods=['POST'], website=True, csrf=True)
    def submit_company_cif_form(self, model_name, **post):
        """Handles the submission for a COMPANY client, supports draw+upload signature."""
        access_token = post.get('cif_token')

        cif_request_session, sale_order = self._get_cif_request_session_for_token(access_token)
        if not cif_request_session or not sale_order:
            _logger.debug('submit_company_cif_form: CIF request token not found access_token=%s', access_token)
            return request.render('bs_cif_process.cif_form_already_submitted_template')

        try:
            cif_request_session._check_active_and_quota()
        except Exception:
            return request.render('bs_cif_process.cif_form_already_submitted_template')

        # Ensure share percentage is validated/available for company CIF
        submitted_percentage = self._parse_percentage(post.get('shareholder_percentage'))
        try:
            self._validate_share_percentage_for_sale_order(sale_order, submitted_percentage)
        except ValueError as e:
            return request.render('bs_cif_process.cif_form_error_template', {
                'error_message': str(e),
                'sale_order_name': sale_order.name,
            })

        cif_request_key = self._get_cif_request_key(cif_request_session)

        try:
            with request.env.cr.savepoint():
                # Process file uploads for supporting documents
                passport_doc_ids = []
                emirates_doc_ids = []

                # Handle passport supporting documents
                passport_files = request.httprequest.files.getlist('passport_docs')
                for passport_file in passport_files:
                    if passport_file and getattr(passport_file, 'filename', None):
                        content = passport_file.read()
                        if content:
                            attachment = request.env['ir.attachment'].sudo().create({
                                'name': passport_file.filename,
                                'type': 'binary',
                                'datas': base64.b64encode(content),
                                'mimetype': passport_file.content_type or 'application/octet-stream',
                            })
                            passport_doc_ids.append(attachment.id)

                # Handle emirates ID supporting documents
                emirates_files = request.httprequest.files.getlist('emirates_id_docs')
                for emirates_file in emirates_files:
                    if emirates_file and getattr(emirates_file, 'filename', None):
                        content = emirates_file.read()
                        if content:
                            attachment = request.env['ir.attachment'].sudo().create({
                                'name': emirates_file.filename,
                                'type': 'binary',
                                'datas': base64.b64encode(content),
                                'mimetype': emirates_file.content_type or 'application/octet-stream',
                            })
                            emirates_doc_ids.append(attachment.id)

                company_vals = {
                    'name': post.get('company_name'),
                    'company_type': 'company',
                    'shareholder_name': post.get('shareholder_name', ''),
                    'is_company': True,
                    'trade_license_no': post.get('trade_license_no',''),
                    'street': post.get('street_name',''),
                    'street2': f"Unit/Villa: {post.get('unit_villa_no','')}, Building: {post.get('building_name', '')}",
                    'city': post.get('city'), 'zip': post.get('postal_code',''),
                    'country_id': int(post.get('country_id')) if post.get('country_id','') else False,
                    'title': post.get('shareholder_title',''),
                    'passport_no': post.get('passport_no'),
                    'passport_supporting_docs': [(6, 0, passport_doc_ids)] if passport_doc_ids else [],
                    'national_id_no': post.get('emirates_no'),
                    'supporting_document_ids': [(6, 0, emirates_doc_ids)] if emirates_doc_ids else [],
                    'email': post.get('email'),
                    'email_address': post.get('email_address') or post.get('alternate_email'),
                    'mobile': post.get('mobile'),
                    'phone': post.get('phone'),
                    'date_of_birth': post.get('date_of_birth') or False,
                    'nationality': int(post.get('nationality_id')) if post.get('nationality_id') else False,
                    'payment_type': post.get('payment_type') or False,
                    'residency_status': post.get('uae_residency_status'),
                }
                signature_b64 = None
                signature_file = request.httprequest.files.get('signature') or \
                                 request.httprequest.files.get('signature[0][0]')
                if signature_file and getattr(signature_file, 'filename', None):
                    content = signature_file.read()
                    if content:
                        signature_b64 = base64.b64encode(content)
                if not signature_b64:
                    raw_b64 = post.get('signature_data')
                    if raw_b64:
                        if raw_b64.startswith('data:'):
                            try:
                                raw_b64 = raw_b64.split(',', 1)[1]
                            except Exception:
                                raw_b64 = ''
                        try:
                            base64.b64decode(raw_b64)
                            signature_b64 = raw_b64.encode()
                        except Exception:
                            signature_b64 = None

                if not signature_b64:
                    return request.render('bs_cif_process.cif_form_error_template', {
                        'error_message': 'Signature is required. Please draw or upload your signature.',
                        'sale_order_name': sale_order.name,
                    })

                company_vals['signature'] = signature_b64

                company_partner = sale_order.partner_id
                company_partner.write(company_vals)

                # Create security question answers for company partner
                security_answers = []
                for i in range(1, 4):
                    question_id = post.get(f'security_question_{i}')
                    answer = post.get(f'security_answer_{i}', '').strip()
                    if question_id and answer:
                        security_answers.append((0, 0, {
                            'sequence': i,
                            'question_id': int(question_id),
                            'answer': answer,
                        }))
                
                if security_answers:
                    company_partner.write({'security_answer_ids': [(5, 0, 0)] + security_answers})

                # ✅ Check capacity BEFORE creating CIF form
                if not self._check_submission_capacity(cif_request_session):
                    return request.render('bs_cif_process.cif_form_already_submitted_template')

                cif_vals = {k: v for k, v in post.items() if hasattr(request.env['cif.form'], k)}
                cif_vals.update({
                    'source_sale_order_id': sale_order.id,
                    'client_type': 'company',
                    'created_partner_id': company_partner.id,
                    'shareholder_percentage': submitted_percentage,
                    'signature': signature_b64,
                    'agent_id': sale_order.agent_id.id if sale_order.agent_id else False,
                    'passport_supporting_docs': [(6, 0, passport_doc_ids)] if passport_doc_ids else [],
                    'supporting_document_ids': [(6, 0, emirates_doc_ids)] if emirates_doc_ids else [],
                    'cif_request_session_id': cif_request_session.id if cif_request_session else False,
                    'residency_status': post.get('uae_residency_status'),
                    'national_id_no': post.get('emirates_no'),
                    # Add verification status from session
                    'is_mobile_verified': request.session.get(f'verified_mobile_{cif_request_key}', False),
                    'is_phone_verified': request.session.get(f'verified_phone_{cif_request_key}', False),
                    'is_email_verified': request.session.get(f'email_verified_email_{cif_request_key}', False),
                })
                
                if security_answers:
                    cif_vals['security_answer_ids'] = security_answers
                
                cif_record = request.env['cif.form'].sudo().create(cif_vals)

                # Link CIF record to Sale Order directly
                sale_order.sudo().write({'cif_form_id': cif_record.id})

                chatter_message = f"Company Information Form {cif_record.cif_no} submitted for: {company_partner.name} (Authorized Signatory: {company_partner.name})."
                # self._post_process_submission(sale_order, cif_record, chatter_message) # signature is not visible. Let's fix it later.
                sale_order.sudo().message_post(
                    body=chatter_message,
                )

                # Send notification to salesperson
                if sale_order.user_id:
                    template = request.env.ref('bs_cif_process.email_template_cif_submitted', raise_if_not_found=False)
                    if template:
                        template.sudo().with_context(
                            cif_form_id=cif_record.id,
                            cif_form_name=cif_record.cif_no,
                        ).send_mail(sale_order.id, force_send=True)
                    
                    # Send in-app notification to salesperson's Odoo notification inbox
                    # sale_order.user_id.partner_id.message_notify(
                    #     body=f"CIF Form {cif_record.cif_no} has been submitted for sale order {sale_order.name}.",
                    #     subtype="mail.mt_note",
                    #     message_type="user_notification",
                    #     subject="CIF Form Submitted",
                    # )

                # Consume CIF request quota atomically AFTER successful submission is persisted
                if cif_request_session:
                    cif_request_session.consume_submission_slot()

        except Exception as e:
            _logger.exception(f"Error during Company CIF submission for SO {sale_order.name}: {e}")
            error_msg = e.args[0] if e.args else 'An unexpected error occurred during form submission.'
            return request.render('bs_cif_process.cif_form_error_template', {
                'error_message': error_msg,
                'sale_order_name': sale_order.name,
            })

        # Render thank you page instead of JSON response
        try:
            return request.render('bs_cif_process.cif_company_thank_you_template', {
                'sale_order_name': sale_order.name,
            })
        except Exception:
            # Fallback: avoid 500 if website-specific template lookup fails.
            return request.render('bs_cif_process.cif_individual_thank_you_template', {
                'sale_order_name': sale_order.name,
            })

    # =========================================================
    # ==                 CHANGE CIF WORKFLOW                  ==
    # =========================================================

    def _get_change_request(self, token):
        if not token:
            return False
        return request.env['cif.change.request'].sudo().search([('token', '=', token)], limit=1)

    def _render_change_email_step(self, change_req, error_message=None, step_token=None):
        reg_email = change_req._get_registered_email()
        return request.render('bs_cif_process.cif_change_email_verify_template', {
            'token': change_req.token,
            'step_token': step_token,
            'masked_email': self._mask_email(reg_email),
            'error_message': error_message,
            'sale_order_name': change_req.sale_order_id.name if change_req.sale_order_id else '',
        })

    def _render_change_security_step(self, change_req, error_message=None, step_token=None):
        """Render security questions verification step for Change CIF."""
        # Get security questions from the CIF form (not from partner)
        cif_form = change_req.cif_form_id
        security_questions = []

        if cif_form and cif_form.security_answer_ids:
            security_questions = [(ans.question_id, ans.sequence) for ans in cif_form.security_answer_ids if ans.question_id]
            security_questions.sort(key=lambda x: x[1])  # Sort by sequence
            security_questions = [q[0] for q in security_questions]  # Extract questions only

        attempts_remaining = None
        if change_req.security_attempts > 0:
            attempts_remaining = max(0, (change_req.security_max_attempts or 5) - change_req.security_attempts)

        return request.render('bs_cif_process.cif_change_security_verify_template', {
            'token': change_req.token,
            'step_token': step_token,
            'security_questions': security_questions,
            'error_message': error_message,
            'attempts_remaining': attempts_remaining,
            'sale_order_name': change_req.sale_order_id.name if change_req.sale_order_id else '',
        })

    @http.route('/client-information-form/change', type='http', auth='public', website=True)
    def render_change_cif_form(self, token=None, step_token=None, **kw):
        # Entry point of the public flow.
        if not token:
            return request.render('website.404')

        change_req = self._get_change_request(token)
        if not change_req:
            return request.render('bs_cif_process.cif_form_already_submitted_template')

        try:
            change_req._check_not_expired()
        except Exception as e:
            # Expired links should show the expired template.
            if getattr(change_req, 'state', '') == 'expired':
                return request.render('bs_cif_process.cif_form_already_submitted_template')
            return request.render('bs_cif_process.cif_form_error_template', {
                'error_message': str(e) or 'This link is no longer valid.',
                'sale_order_name': change_req.sale_order_id.name if change_req.sale_order_id else '',
            })

        sale_order = change_req.sale_order_id
        if not sale_order or not sale_order.cif_form_id or not sale_order.partner_id:
            return request.render('bs_cif_process.cif_form_already_submitted_template')

        # Default behavior: always start from Step 1 (email verification) when opening the public link
        # unless the caller provided a valid 'form' step token (for deep links or internal navigation).
        if step_token:
            try:
                # Only allow immediate form access when a valid 'form' token is presented.
                change_req._assert_step_token('form', step_token)
                # Consume form token (single-use) and continue to render the change form.
                change_req.consume_step_token('form', step_token)
            except Exception:
                # Invalid form token -> fall back to step 1 (email verification)
                email_step_token = change_req.issue_step_token('email', ttl_minutes=15)
                return self._render_change_email_step(change_req, step_token=email_step_token)
        else:
            # No form token provided: always render email verification as the entry point.
            email_step_token = change_req.issue_step_token('email', ttl_minutes=15)
            return self._render_change_email_step(change_req, step_token=email_step_token)

        change_req.mark_opened(ip=request.httprequest.remote_addr, ua=request.httprequest.user_agent.string)

        cif = change_req.cif_form_id
        partner = change_req.partner_id

        render_values = self._get_render_values(sale_order)
        # Gather existing security answers from the CIF record (sequence -> {question_id, answer})
        existing_security = {}
        if partner and hasattr(partner, 'security_answer_ids') and partner.security_answer_ids:
            for ans in partner.security_answer_ids:
                try:
                    seq = int(getattr(ans, 'sequence', False) or 0)
                except Exception:
                    seq = 0
                if seq:
                    existing_security[seq] = {
                        'question_id': ans.question_id.id if ans.question_id else False,
                        'answer': ans.answer or ''
                    }
        render_values.update({
            'existing_security': existing_security,
        })
        render_values.update({
            'is_change_mode': True,
            'change_token': token,
            # New submission step token (single-use)
            'change_step_token': change_req.issue_step_token('submit', ttl_minutes=30),
            'existing_cif': cif,
            'existing_partner': partner,
            'readonly_email': True,
            'readonly_share_percentage': True,
            'prefill_share_percentage': purchaser_line.share_percentage,
        })

        # Render correct template based on client_type
        if cif.client_type == 'company':
            return request.render('bs_cif_process.cif_company_form_template', render_values)
        return request.render('bs_cif_process.cif_form_template', render_values)

    @http.route('/client-information-form/change/verify-email', type='http', auth='public', website=True, methods=['POST'], csrf=True)
    def change_cif_verify_email(self, **post):
        token = post.get('token')
        step_token = post.get('step_token')
        entered = self._sanitize_email(post.get('email_input'))
        change_req = self._get_change_request(token)
        if not change_req:
            return request.render('bs_cif_process.cif_form_already_submitted_template')

        try:
            change_req._check_not_expired()
            # Enforce step token (single-use)
            change_req.consume_step_token('email', step_token)
        except Exception as e:
            # Re-issue fresh token for email step.
            email_step_token = change_req.issue_step_token('email', ttl_minutes=15)
            return self._render_change_email_step(change_req, error_message=str(e) or 'This link is no longer valid.', step_token=email_step_token)

        registered = change_req._get_registered_email()
        if not entered or entered != registered:
            email_step_token = change_req.issue_step_token('email', ttl_minutes=15)
            return self._render_change_email_step(change_req, error_message='Email does not match our records. Please enter the exact email address.', step_token=email_step_token)

        # ✅ Email verified - mark as verified and skip OTP, go directly to security questions
        change_req.write({
            'is_email_verified': True,
            'email_verified_at': fields.Datetime.now(),
        })

        # Issue security step token and redirect to security questions
        security_step_token = change_req.issue_step_token('security', ttl_minutes=15)
        return request.redirect(f"/client-information-form/change/security-questions?token={change_req.token}&step_token={security_step_token}")

    @http.route('/client-information-form/change/security-questions', type='http', auth='public', website=True, methods=['GET'])
    def change_cif_security_questions(self, token=None, step_token=None, **kw):
        """Display security questions verification step."""
        change_req = self._get_change_request(token)
        if not change_req:
            return request.render('bs_cif_process.cif_form_already_submitted_template')

        try:
            change_req._check_not_expired()
            change_req._assert_step_token('security', step_token)
        except Exception as e:
            # Redirect back to email verification
            email_step_token = change_req.issue_step_token('email', ttl_minutes=15)
            return self._render_change_email_step(change_req, error_message=str(e), step_token=email_step_token)

        # Check if security verification is locked
        if change_req.security_locked_until and fields.Datetime.now() < change_req.security_locked_until:
            return request.render('bs_cif_process.cif_verification_locked_template', {
                'locked_until': self._format_datetime_for_user(change_req.security_locked_until),
                'sale_order_name': change_req.sale_order_id.name if change_req.sale_order_id else '',
            })

        return self._render_change_security_step(change_req, step_token=step_token)

    @http.route('/client-information-form/change/verify-security', type='http', auth='public', website=True, methods=['POST'], csrf=True)
    def change_cif_verify_security(self, **post):
        """Verify security question answers for Change CIF."""
        token = post.get('token')
        step_token = post.get('step_token')
        change_req = self._get_change_request(token)

        if not change_req:
            return request.render('bs_cif_process.cif_form_already_submitted_template')

        try:
            change_req._check_not_expired()
            change_req.consume_step_token('security', step_token)
        except Exception as e:
            security_step_token = change_req.issue_step_token('security', ttl_minutes=15)
            return self._render_change_security_step(change_req, error_message=str(e), step_token=security_step_token)

        # Build answers dictionary from POST data
        answers_dict = {}
        for key, value in post.items():
            if key.startswith('answer_'):
                question_id = key.replace('answer_', '')
                answers_dict[question_id] = value

        try:
            change_req.verify_security_questions(answers_dict)
        except Exception as e:
            security_step_token = change_req.issue_step_token('security', ttl_minutes=15)
            return self._render_change_security_step(change_req, error_message=str(e), step_token=security_step_token)

        # Security verification successful - issue form access token
        form_token = change_req.issue_step_token('form', ttl_minutes=30)
        return request.redirect(f"/client-information-form/change?token={change_req.token}&step_token={form_token}")

    @http.route('/cif/submit/change', type='http', auth='public', methods=['POST'], website=True, csrf=True)
    def submit_change_cif_form(self, **post):
        token = post.get('change_token')
        step_token = post.get('change_step_token')
        change_req = self._get_change_request(token)
        if not change_req:
            return request.render('bs_cif_process.cif_form_already_submitted_template')

        try:
            change_req._check_not_expired()
            # Must be in correct workflow state and have a valid submit token.
            # if change_req.workflow_state != 'form_opened':
            #     raise ValidationError('Invalid step. Please restart the Change CIF process from the email link.')
            change_req.consume_step_token('submit', step_token)
        except Exception as e:
            return request.render('bs_cif_process.cif_form_error_template', {
                'error_message': str(e),
                'sale_order_name': change_req.sale_order_id.name if change_req.sale_order_id else '',
            })

        # Step gate: require email ownership verification before accepting changes.
        if not getattr(change_req, 'is_email_verified', False):
            email_step_token = change_req.issue_step_token('email', ttl_minutes=15)
            return self._render_change_email_step(change_req, error_message='Please verify your email to continue.', step_token=email_step_token)

        # ✅ NEW: Require security questions verification before accepting changes
        try:
            change_req._check_security_verified()
        except ValidationError as e:
            security_step_token = change_req.issue_step_token('security', ttl_minutes=15)
            return self._render_change_security_step(change_req, error_message=str(e), step_token=security_step_token)

        sale_order = change_req.sale_order_id
        cif = change_req.cif_form_id

        # Always update the partner tagged with the CIF (single source of truth for CIF owner)
        partner = cif.created_partner_id or change_req.partner_id

        if not (sale_order and cif and partner):
            return request.render('bs_cif_process.cif_form_already_submitted_template')

        # Enforce read-only fields server-side
        # If a new email was verified through OTP, use that; otherwise keep the old email
        if getattr(change_req, 'is_new_email_verified', False) and change_req.new_email:
            immutable_email = (change_req.new_email or '').strip().lower()
        else:
            immutable_email = (partner.email or '').strip().lower()
        immutable_share = 100.0

        try:
            with request.env.cr.savepoint():
                # Handle uploads similarly to main flow; here we only update if provided.
                passport_doc_ids = []
                emirates_doc_ids = []

                passport_files = request.httprequest.files.getlist('passport_docs')
                for passport_file in passport_files:
                    if passport_file and getattr(passport_file, 'filename', None):
                        content = passport_file.read()
                        if content:
                            attachment = request.env['ir.attachment'].sudo().create({
                                'name': passport_file.filename,
                                'type': 'binary',
                                'datas': base64.b64encode(content),
                                'mimetype': passport_file.content_type or 'application/octet-stream',
                            })
                            passport_doc_ids.append(attachment.id)

                emirates_files = request.httprequest.files.getlist('emirates_id_docs')
                for emirates_file in emirates_files:
                    if emirates_file and getattr(emirates_file, 'filename', None):
                        content = emirates_file.read()
                        if content:
                            attachment = request.env['ir.attachment'].sudo().create({
                                'name': emirates_file.filename,
                                'type': 'binary',
                                'datas': base64.b64encode(content),
                                'mimetype': emirates_file.content_type or 'application/octet-stream',
                            })
                            emirates_doc_ids.append(attachment.id)

                # Optional signature update: only overwrite if provided.
                signature_b64 = None
                signature_file = request.httprequest.files.get('signature') or request.httprequest.files.get('signature[0][0]')
                if signature_file and getattr(signature_file, 'filename', None):
                    content = signature_file.read()
                    if content:
                        signature_b64 = base64.b64encode(content)
                if not signature_b64:
                    raw_b64 = post.get('signature_data')
                    if raw_b64:
                        if raw_b64.startswith('data:'):
                            try:
                                raw_b64 = raw_b64.split(',', 1)[1]
                            except Exception:
                                raw_b64 = ''
                        try:
                            base64.b64decode(raw_b64)
                            signature_b64 = raw_b64.encode()
                        except Exception:
                            signature_b64 = None

                # Partner updates (email is immutable)
                partner_vals = {
                    'mobile': post.get('mobile') or partner.mobile,
                    'phone': post.get('phone') or partner.phone,
                    'email': immutable_email or partner.email,
                    'email_address': post.get('email_address') or getattr(partner, 'email_address', False),
                    'street': post.get('street_name') or partner.street,
                    'city': post.get('city') or partner.city,
                    'zip': post.get('postal_code') or partner.zip,
                    'passport_no': post.get('passport_no') or getattr(partner, 'passport_no', False),
                    'national_id_no': post.get('emirates_no') or getattr(partner, 'national_id_no', False),
                    'middle_name': post.get('middle_name') or getattr(partner, 'middle_name', False),
                    'date_of_birth': post.get('date_of_birth') or getattr(partner, 'date_of_birth', False),
                    'gender': post.get('gender') or getattr(partner, 'gender', False),
                    'shareholder_name': post.get('shareholder_name') or getattr(partner, 'shareholder_name', False),
                    'nationality': int(post.get('nationality_id')) if post.get('nationality_id') else getattr(partner, 'nationality', False) and partner.nationality.id,
                    'country_id': int(post.get('country_id')) if post.get('country_id') else partner.country_id.id,
                    'payment_type': post.get('payment_type') or getattr(partner, 'payment_type', False),
                    'residency_status': post.get('uae_residency_status') or getattr(partner, 'residency_status', False),
                    'source_of_income': post.get('source_of_income') or getattr(partner, 'source_of_income', False),
                }

                # Update name fields when provided (keep email/share read-only)
                first_name = (post.get('first_name') or '').strip()
                last_name = (post.get('last_name') or '').strip()
                if first_name or last_name:
                    partner_vals['name'] = f"{first_name} {last_name}".strip()

                company_name = (post.get('company_name') or '').strip()
                if company_name:
                    partner_vals['name'] = company_name

                if signature_b64:
                    partner_vals['signature'] = signature_b64
                if passport_doc_ids:
                    partner_vals['passport_supporting_docs'] = [(6, 0, passport_doc_ids)]
                if emirates_doc_ids:
                    partner_vals['supporting_document_ids'] = [(6, 0, emirates_doc_ids)]

                partner.sudo().write(partner_vals)

                # CIF updates with same payload (keep share/email immutable)
                # Sync all relevant fields between partner and CIF for data consistency
                cif_vals = {
                    'source_sale_order_id': sale_order.id,
                    'created_partner_id': partner.id,
                    # Immutable fields
                    'email': immutable_email or cif.email,
                    'shareholder_percentage': immutable_share,
                    # Contact Information
                    'mobile': post.get('mobile') or cif.mobile,
                    'phone': post.get('phone') or cif.phone,
                    'email_address': post.get('email_address') or cif.email_address,
                    # Name Fields
                    'first_name': post.get('first_name') or cif.first_name,
                    'last_name': post.get('last_name') or cif.last_name,
                    'middle_name': post.get('middle_name') or cif.middle_name,
                    'shareholder_name': post.get('shareholder_name') or cif.shareholder_name,
                    'company_name': post.get('company_name') or cif.company_name,
                    # Identity Documents
                    'passport_no': post.get('passport_no') or cif.passport_no,
                    'national_id_no': post.get('emirates_no') or cif.national_id_no,
                    'residency_status': post.get('uae_residency_status') or cif.residency_status,
                    'nationality_id': int(post.get('nationality_id')) if post.get('nationality_id') else cif.nationality_id.id if cif.nationality_id else False,
                    # Address Information
                    'unit_villa_no': post.get('unit_villa_no') or cif.unit_villa_no,
                    'building_name': post.get('building_name') or cif.building_name,
                    'street_name': post.get('street_name') or cif.street_name,
                    'city': post.get('city') or cif.city,
                    'postal_code': post.get('postal_code') or cif.postal_code,
                    'country_id': int(post.get('country_id')) if post.get('country_id') else cif.country_id.id if cif.country_id else False,
                }
                # Collect security question answers from POST and replace existing ones on the CIF record
                security_answers = []
                for i in range(1, 4):
                    qid = post.get(f'security_question_{i}')
                    ans = (post.get(f'security_answer_{i}') or '').strip()
                    if qid and ans:
                        try:
                            security_answers.append((0, 0, {
                                'sequence': i,
                                'question_id': int(qid),
                                'answer': ans,
                            }))
                        except Exception:
                            # ignore invalid values
                            pass
                if security_answers:
                    # Replace existing answers with new set
                    cif_vals['security_answer_ids'] = [(5, 0, 0)] + security_answers
                if signature_b64:
                    cif_vals['signature'] = signature_b64
                if passport_doc_ids:
                    cif_vals['passport_supporting_docs'] = [(6, 0, passport_doc_ids)]
                if emirates_doc_ids:
                    cif_vals['supporting_document_ids'] = [(6, 0, emirates_doc_ids)]

                cif.sudo().write(cif_vals)

                # Mark workflow as submitted/done.
                change_req._transition_workflow('submitted')
                change_req.mark_done(ip=request.httprequest.remote_addr, ua=request.httprequest.user_agent.string)

        except Exception as e:
            _logger.exception(f"Error during Change CIF submission: {e}")
            error_msg = e.args[0] if e.args else 'An unexpected error occurred during Change CIF submission.'
            return request.render('bs_cif_process.cif_form_error_template', {
                'error_message': error_msg,
                'sale_order_name': sale_order.name,
            })

        return request.render('bs_cif_process.cif_individual_thank_you_template', {
            'sale_order_name': sale_order.name,
        })


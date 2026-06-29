# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from .utils import PAYMENT_TYPE_OPTIONS

class ClientInformationForm(models.Model):
    _name = 'cif.form'
    _description = 'Client Information Form'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'cif_no'

    cif_no = fields.Char(string='CIF No.', readonly=True, required=True, copy=False, default='New')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected')
    ], string='Status', default='draft', required=True, tracking=True, copy=False)
    source_sale_order_id = fields.Many2one('sale.order', string='Source Sale Order', required=True, ondelete='cascade', tracking=True)
    created_partner_id = fields.Many2one('res.partner', string='Created Contact', readonly=True, copy=False,
                                         help="The primary contact (individual or company) created from this form.", tracking=True)

    client_type = fields.Selection([
        ('person', 'Individual'),
        ('company', 'Company')
    ], string='Client Type', default='person', required=True, tracking=True)

    # === COMPANY DETAILS (used when client_type is 'company') ===
    company_name = fields.Char(string='Company Name', tracking=True)
    trade_license_no = fields.Char(string='Trade License No.', tracking=True)
    shareholder_title = fields.Many2one('res.partner.title', string='Title', tracking=True)
    shareholder_percentage = fields.Float(string='Shareholder %', tracking=True)

    # === EXISTING FIELDS (now for 'Individual' or 'Shareholder') ===
    # For Individuals: This is their first name.
    # For Companies: This is the shareholder's first name.
    shareholder_name = fields.Char(string='Shareholder Name', tracking=True)
    first_name = fields.Char(string='First Name', tracking=True)
    middle_name = fields.Char(string='Middle Name', tracking=True)
    last_name = fields.Char(string='Last Name', tracking=True)
    passport_no = fields.Char(string='Passport No.', tracking=True)
    passport_supporting_docs = fields.Many2many('ir.attachment', 'cif_form_passport_docs_rel', 'cif_form_id', 'attachment_id', string='Passport Supporting Documents', tracking=True)
    national_id_no = fields.Char(string='National ID Number', tracking=True)
    supporting_document_ids = fields.Many2many('ir.attachment', 'cif_form_supporting_docs_rel', 'cif_form_id', 'attachment_id', string='Supporting Documents', tracking=True)
    nationality_id = fields.Many2one('res.country', string='Nationality', tracking=True)
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other')
    ], string='Gender', tracking=True)
    unit_no = fields.Char(string='Unit No.', tracking=True)
    payment_plan = fields.Many2one(
        comodel_name='installment.option',
        string='Payment Plan', related='source_sale_order_id.installment_option_custom', tracking=True)

    # === CLIENT/COMPANY ADDRESS ===
    unit_villa_no = fields.Char(string='Unit / Villa No', tracking=True)
    building_name = fields.Char(string='Building Name', tracking=True)
    street_name = fields.Char(string='Street Name', tracking=True)
    city = fields.Char(string='City', tracking=True)
    country_id = fields.Many2one('res.country', string='Country', tracking=True)
    postal_code = fields.Char(string='Postal Code / Zip Code', tracking=True)
    payment_type = fields.Selection(PAYMENT_TYPE_OPTIONS, string='Preferred Payment Type', tracking=True)
    # payment_method_line_id = fields.Many2one(
    #     comodel_name='account.payment.method.line',
    #     string='Mode of Payment',
    #     domain="[('payment_method_id.payment_type', '=', 'inbound')]",
    #     help="The method the client will use to make payments (e.g., Bank Transfer, Credit Card).",
    #     tracking=True
    # )
    po_box = fields.Char(string='P.O. Box', tracking=True)

    # === CONTACT & OTHER (for 'Individual' or 'Shareholder') ===
    mobile = fields.Char(string='Mobile No.', required=True, tracking=True)
    phone = fields.Char(string='Alt. Mobile No.', tracking=True)
    email = fields.Char(string='Email', required=True, tracking=True)
    email_address = fields.Char(string='Alt. Email', tracking=True)
    date_of_birth = fields.Date(string='Date of Birth', tracking=True)
    source_of_income = fields.Char(string='Source of Income', tracking=True)
    residency_status = fields.Selection([
        ('resident', 'Resident'),
        ('non_resident', 'Non Resident')
    ], string='Residency Status', tracking=True)
    signature = fields.Binary(string='Signature Image', attachment=True)

    # === PHONE VERIFICATION FIELDS ===
    is_mobile_verified = fields.Boolean(string='Mobile Verified', default=False, tracking=True)
    is_phone_verified = fields.Boolean(string='Phone Verified', default=False, tracking=True)

    # === EMAIL VERIFICATION FIELDS ===
    is_email_verified = fields.Boolean(string='Email Verified', default=False, tracking=True)
    is_email_address_verified = fields.Boolean(string='Alt Email Verified', default=False, tracking=True)

    # === AGENCY DETAILS ===
    agent_id = fields.Many2one(
        'res.partner',
        string="Agency",
        related='source_sale_order_id.agent_id',
    )
    agent_code = fields.Char(
        string="Agent ID",
        related='agent_id.agent_code',
        readonly=False,
        store=True,
        tracking=True
    )
    agent_name = fields.Char(string="Agent Name", readonly=False)
    agent_trade_license_no = fields.Char(string="Trade License Registration No.", related='agent_id.trade_license_no')
    agent_mobile = fields.Char(string='Agent Mobile', related='agent_id.mobile')
    agent_email = fields.Char(string='Agent Email', related='agent_id.email')
    
    
    # === SECURITY QUESTIONS ===
    security_answer_ids = fields.One2many(
        'security.question.answer',
        'cif_form_id',
        string='Security Questions & Answers',
        tracking=True
    )

    cif_change_request_ids = fields.One2many(
        'cif.change.request',
        'cif_form_id',
        string='CIF Change Requests',
        readonly=True,
        copy=False,
        help='History of CIF change requests sent for this CIF form.'
    )

    cif_change_request_count = fields.Integer(
        string='CIF Change Request Count',
        compute='_compute_cif_change_request_count'
    )

    cif_request_session_id = fields.Many2one(
        'cif.request.session',
        string='CIF Request Session',
        readonly=True,
        copy=False,
        index=True,
        ondelete='set null',
        help='The CIF request that generated the public access token used for this submission.',
        tracking=True,
    )

    @api.onchange('agent_id')
    def _onchange_agent_id(self):
        for cif in self:
            if cif.agent_id and cif.agent_id.representative:
                cif.agent_name = cif.agent_id.representative.name
            else:
                cif.agent_name = False
                
                
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('cif_no', 'New') == 'New':
                sequence = self.env['ir.sequence'].next_by_code('cif.form.sequence') or 'New'
                vals['cif_no'] = sequence + '-[' + vals.get('unit_no', False) + ']'
        return super().create(vals_list)

    def write(self, vals):
        """Override write to reset verification when phone numbers and emails change"""
        for record in self:
            # Check if email is being changed
            if 'email' in vals and vals['email'] != record.email:
                vals['is_email_verified'] = False
                # Clean up any existing OTP records for email
                record.env['email.otp'].search([
                    ('email_address', '=', record.email),
                    ('field_type', '=', 'email'),
                    ('cif_form_id', '=', record.id)
                ]).unlink()

            # Check if email_address is being changed
            if 'email_address' in vals and vals['email_address'] != record.email_address:
                vals['is_email_address_verified'] = False
                # Clean up any existing OTP records for email_address
                record.env['email.otp'].search([
                    ('email_address', '=', record.email_address),
                    ('field_type', '=', 'email_address'),
                    ('cif_form_id', '=', record.id)
                ]).unlink()

        return super().write(vals)

    def action_send_email_otp(self):
        """Generate and send OTP for email verification"""
        if not self.email:
            raise UserError("Please enter an email address first.")

        # Generate OTP
        otp_record = self.env['email.otp'].generate_otp(
            email_address=self.email,
            field_type='email',
            cif_form_id=self.id
        )

        # Send OTP via email
        result = otp_record.send_otp_via_email()

        if result['success']:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': result['message'],
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': result['message'],
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def action_send_email_address_otp(self):
        """Generate and send OTP for alternate email verification"""
        if not self.email_address:
            raise UserError("Please enter an alternate email address first.")

        # Generate OTP
        otp_record = self.env['email.otp'].generate_otp(
            email_address=self.email_address,
            field_type='email_address',
            cif_form_id=self.id
        )

        # Send OTP via email
        result = otp_record.send_otp_via_email()

        if result['success']:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': result['message'],
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': result['message'],
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def action_verify_email_otp(self, otp_code):
        """Verify email OTP"""
        if not otp_code:
            return {
                'success': False,
                'message': 'Please enter the verification code.'
            }

        # Find the latest OTP record for email
        otp_record = self.env['email.otp'].search([
            ('email_address', '=', self.email),
            ('field_type', '=', 'email'),
            ('cif_form_id', '=', self.id)
        ], limit=1, order='created_date desc')

        if not otp_record:
            return {
                'success': False,
                'message': 'No verification code found. Please request a new code.'
            }

        # Verify OTP
        result = otp_record.verify_otp(otp_code)

        if result['success']:
            self.is_email_verified = True
            # Clean up the OTP record after successful verification
            otp_record.unlink()

        return result

    def action_verify_email_address_otp(self, otp_code):
        """Verify alternate email OTP"""
        if not otp_code:
            return {
                'success': False,
                'message': 'Please enter the verification code.'
            }

        # Find the latest OTP record for email_address
        otp_record = self.env['email.otp'].search([
            ('email_address', '=', self.email_address),
            ('field_type', '=', 'email_address'),
            ('cif_form_id', '=', self.id)
        ], limit=1, order='created_date desc')

        if not otp_record:
            return {
                'success': False,
                'message': 'No verification code found. Please request a new code.'
            }

        # Verify OTP
        result = otp_record.verify_otp(otp_code)

        if result['success']:
            self.is_email_address_verified = True
            # Clean up the OTP record after successful verification
            otp_record.unlink()

        return result

    def _compute_cif_change_request_count(self):
        for rec in self:
            rec.cif_change_request_count = len(rec.cif_change_request_ids)

    def _check_sale_order_in_cif(self):
        self.ensure_one()
        if self.source_sale_order_id and self.source_sale_order_id.state and self.source_sale_order_id.state != 'in_cif':
            raise ValidationError(_(
                "Sale Order must be in 'In CIF' state before changing CIF status."
            ))

    def action_set_accepted(self):
        self._check_sale_order_in_cif()
        self.write({'state': 'accepted'})
        if self.source_sale_order_id:
            self.source_sale_order_id.write({
                'kyc_verified': True,
                'kyc_rejected': False,
            })
        return True

    def action_set_rejected(self):
        self.ensure_one()
        self._check_sale_order_in_cif()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reject CIF'),
            'res_model': 'cif.form.reject.reason.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_cif_form_id': self.id,
            },
        }

    def action_set_draft(self):
        self._check_sale_order_in_cif()
        self.write({'state': 'draft'})
        if self.source_sale_order_id:
            self.source_sale_order_id.write({
                'kyc_verified': False,
                'kyc_rejected': False,
            })
        return True

    def action_reject_with_reason(self, reason):
        self.ensure_one()
        self._check_sale_order_in_cif()
        self.write({'state': 'rejected'})
        if self.source_sale_order_id:
            self.source_sale_order_id.write({
                'kyc_verified': False,
                'kyc_rejected': True,
            })
        self.message_post(
            body=_('CIF rejected. Reason: %s') % (reason or _('No reason provided.')),
            subject=_('CIF Rejected'),
            subtype_xmlid='mail.mt_note',
        )
        return True

    def action_send_cif_change_request(self):
        """
        Open the CIF Change Request email composer.

        Delegates entirely to ``cif.change.request._build_cif_change_composer_action``
        so that the token/body/action logic lives in exactly one place.
        """
        self.ensure_one()

        sale_order = self.source_sale_order_id
        if not sale_order:
            raise UserError(_("No Sale Order is linked to this CIF form."))

        partner = self.created_partner_id or sale_order.partner_id
        if not partner:
            raise UserError(_("No partner is associated with this CIF form / Sale Order."))

        email_to = (partner.email or '').strip() if partner else ''
        if not email_to:
            raise UserError(_(
                "No email address found for partner '%s'. "
                "Please set an email before sending a CIF change request."
            ) % (partner.display_name if partner else ''))

        return self.env['cif.change.request']._build_cif_change_composer_action(
            sale_order=sale_order,
            partner=partner,
            email_to=email_to,
        )

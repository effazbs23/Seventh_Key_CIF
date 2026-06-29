# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class SaleOrder(models.Model):
    """Extend sale.order with CIF form and session tracking fields."""

    _inherit = 'sale.order'

    state = fields.Selection(selection_add=[
        ('sale', "Sales Order"),
        ('in_cif', 'In CIF'),
        ('in_eoi', 'In EOI'),
        ('booking_sent', 'Booking Sent'),
        ('booking_signed', 'Booking Signed'),
        ('spa_sent', 'SPA Sent'),
        ('spa_signed', 'SPA Signed'),
    ])

    # KYC fields
    kyc_mail_sent = fields.Boolean(string='KYC Mail Sent', copy=False)
    kyc_verified = fields.Boolean(string='KYC Verified', copy=False)
    kyc_rejected = fields.Boolean(string='KYC Rejected', copy=False)
    kyc_verification_documents_ids = fields.Many2many(
        'ir.attachment',
        'sale_order_kyc_docs_rel',
        'sale_order_id',
        'attachment_id',
        string='KYC Verification Documents'
    )

    # Booking / SPA / EOI fields
    booking_form_id = fields.Many2one('cif.form', string='Booking Form', copy=False)
    spa_form_id = fields.Many2one('cif.form', string='SPA Form', copy=False)
    eoi_form_id = fields.Many2one('cif.form', string='EOI Form', copy=False)
    has_archived_booking = fields.Boolean(string='Has Archived Booking', copy=False)
    has_archived_spa = fields.Boolean(string='Has Archived SPA', copy=False)
    has_archived_eoi = fields.Boolean(string='Has Archived EOI', copy=False)

    # EOI sessions
    eoi_request_session_ids = fields.One2many(
        'eoi.request.session',
        'sale_order_id',
        string='EOI Request Sessions',
        copy=False,
    )
    eoi_request_session_count = fields.Integer(
        string='EOI Request Count',
        compute='_compute_eoi_request_session_count',
        store=False,
    )

    def _compute_eoi_request_session_count(self):
        for order in self:
            order.eoi_request_session_count = len(order.eoi_request_session_ids)

    # Accounting fields
    escrow_account = fields.Many2one('account.account', string='Escrow Account')
    registration_fees_account = fields.Many2one('account.account', string='Registration Fees Account')
    additional_currency_id = fields.Many2one('res.currency', string='Additional Currency')
    third_currency_id = fields.Many2one('res.currency', string='Third Currency')
    total_discount_amount = fields.Monetary(string='Total Discount', currency_field='currency_id', compute='_compute_total_discount', store=False)

    def _compute_total_discount(self):
        for order in self:
            order.total_discount_amount = sum(order.order_line.mapped('discount_total'))

    booking_date = fields.Date(string='Booking Date', copy=False)
    project_id = fields.Many2one('project.project', string='Project', index=True)
    is_extra_discount_approved = fields.Boolean(string='Extra Discount Approved', default=False)

    # Agency / representative fields
    agent_id = fields.Many2one(
        'res.partner',
        string="Agency Name",
        domain="[('is_re_agency', '=', True)]"
    )
    agent_code = fields.Char(
        string="Agent ID",
        related='agent_id.agent_code',
        readonly=False,
        store=True
    )
    agency_representative_name = fields.Char(
        string='Agency Representative',
        related='agent_id.representative.name',
        readonly=False,
        store=True,
    )
    is_spa_ready = fields.Boolean(string='SPA Ready', default=False)

    # Share percentage (default to 100% for the single partner)
    share_percentage = fields.Float(
        'Share Percentage',
        default=100.0,
    )

    # Installment option
    installment_option_custom = fields.Many2one(
        'installment.option',
        string='Payment Plan',
    )

    # CIF Form related fields
    cif_form_id = fields.Many2one(
        'cif.form',
        string='CIF Form',
        help='Main CIF form record linked to this sale order'
    )

    # Sessions are the single source of truth for CIF tokens + quotas.
    cif_request_session_ids = fields.One2many(
        'cif.request.session',
        'sale_order_id',
        string='CIF Request Sessions',
        copy=False,
        help='All CIF request sessions created for this sale order with token-based access'
    )

    # Computed field for displaying CIF request count
    cif_request_session_count = fields.Integer(
        string='CIF Request Count',
        compute='_compute_cif_request_session_count',
        store=False,
        help='Number of CIF request sessions'
    )

    # Computed fields for CIF submissions
    cif_allowed_submissions = fields.Integer(
        string='Allowed Submissions',
        compute='_compute_cif_submissions',
        store=False,
        help='Total allowed CIF submissions for this sale order'
    )

    cif_submitted_count = fields.Integer(
        string='Submitted Count',
        compute='_compute_cif_submissions',
        store=False,
        help='Total CIF submissions for this sale order'
    )

    cif_mail_sent_to = fields.Char(
        string='CIF Mail Sent To',
        help='Comma-separated list of email addresses to whom CIF form was sent',
        copy=False,
    )

    cif_mail_sent_cc = fields.Char(
        string='CIF Mail CC',
        help='Comma-separated list of email addresses who received CIF form as CC',
        copy=False,
    )

    has_cif_form = fields.Boolean(
        string='Has CIF Form',
        compute='_compute_has_cif_form',
        store=False,
        help='Check if any purchaser has a CIF form linked'
    )

    @api.depends('cif_request_session_ids.allowed_submissions', 'cif_request_session_ids.submitted_count')
    def _compute_cif_submissions(self):
        for order in self:
            sessions = order.cif_request_session_ids
            order.cif_allowed_submissions = sum(sessions.mapped('allowed_submissions'))
            order.cif_submitted_count = sum(sessions.mapped('submitted_count'))

    def _compute_cif_request_session_count(self):
        for order in self:
            order.cif_request_session_count = len(order.cif_request_session_ids)

    def _compute_has_cif_form(self):
        for order in self:
            order.has_cif_form = bool(order.cif_form_id) or bool(self.env['cif.form'].search([('source_sale_order_id', '=', order.id)]))


    def create_cif_request_session(self, customer_type, allowed_submissions=1):
        """Create a new independent CIF request session for this sale order.

        Contract:
        - Tokens belong to sessions, never to the sale order.
        - This creates a new session each time it's called.
        - Older sessions remain unchanged; each expires via its own quota/state.

        Args:
            customer_type: 'person' or 'company'
            allowed_submissions: Number of CIF submissions allowed for this request (required)

        Returns: cif.request.session record
        """
        self.ensure_one()

        allowed = max(1, int(allowed_submissions or 1))

        session = self.env['cif.request.session'].sudo().create({
            'sale_order_id': self.id,
            'allowed_submissions': allowed,
            'customer_type': customer_type,
        })
        return session

    def get_cif_form_url(self, customer_type, session):
        """Construct the CIF form URL for a specific request session.

        NOTE: session is required to avoid any 'active session' ambiguity.
        """
        self.ensure_one()
        if not session or session.sale_order_id.id != self.id:
            raise ValidationError(_('Invalid CIF request session.'))

        token = session.cif_token
        link = f"{self.get_base_url()}/client-information-form/individual?token={token}"
        if customer_type and customer_type == 'company':
            link = f"{self.get_base_url()}/client-information-form/company?token={token}"
        return link

    def action_send_cif_form(self, customer_type, allowed_submissions=1):
        """Send CIF form with specified quota.

        Args:
            customer_type: 'person' or 'company'
            allowed_submissions: Number of CIF submissions allowed for this request
        """
        self.ensure_one()

        # Always generate a NEW session per request.
        session = self.create_cif_request_session(
            customer_type=customer_type,
            allowed_submissions=int(allowed_submissions or 1)
        )

        base_url = self.get_cif_form_url(customer_type, session=session)

        if not self.agent_id:
            raise UserError(_("An Agent must be assigned to the Sale Order before sending the CIF form."))
        if not self.agent_id.email:
            raise UserError(_("The assigned Agent '%s' must have a valid email address to receive the CIF form link.") % self.agent_id.name)

        template = self.env.ref('bs_cif_process.email_template_cif_form')

        ctx = {
            'default_model': 'sale.order',
            'default_res_ids': self.ids,
            'default_partner_ids': [self.agent_id.id],
            'default_use_template': True,
            'default_template_id': template.id,
            'default_composition_mode': 'comment',
            'base_url': base_url,
            'force_email': True,
            'mark_so_as_in_cif': True,
            'is_cif_mail': True,
            'cif_request_session_id': session.id,
        }

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mail.compose.message',
            'views': [(False, 'form')],
            'view_id': False,
            'target': 'new',
            'context': ctx,
        }

    def action_view_cif_forms(self):
        self.ensure_one()
        cif_records = self.cif_form_id or self.env['cif.form'].search([('source_sale_order_id', '=', self.id)])
        if not cif_records:
            raise UserError(_("No CIF Form is linked to this Sale Order yet."))

        # If only one CIF exists, open it directly in form view.
        if len(cif_records) == 1:
            return {
                'name': _('Client Information Form'),
                'type': 'ir.actions.act_window',
                'res_model': 'cif.form',
                'res_id': cif_records.id,
                'view_mode': 'form',
                'target': 'current',
            }

        # Otherwise, show the list with ability to open forms.
        return {
            'name': _('Client Information Forms'),
            'type': 'ir.actions.act_window',
            'res_model': 'cif.form',
            'view_mode': 'list,form',
            'domain': [('id', 'in', cif_records.ids)],
            'target': 'current',
        }

    def action_view_cif_request_sessions(self):
        """Open CIF request sessions linked to this sale order."""
        self.ensure_one()
        action = self.env.ref('bs_cif_process.action_cif_request_session').read()[0]
        action['domain'] = [('sale_order_id', '=', self.id)]
        action['context'] = {
            'default_sale_order_id': self.id,
        }
        return action


    @api.returns('mail.message', lambda value: value.id)
    def message_post(self, **kwargs):
        res = super(SaleOrder, self).message_post(**kwargs)
        if res and self.env.context.get('mark_so_as_in_cif'):
            self.action_start_cif_collection()
        return res
    
    
      # Constraint removed - purchasers_count field no longer exists on sale.order
    # Quota is now set per CIF request via the send wizard

    def cif_form_mail(self):
        """Button handler for 'Send CIF Form' on Sale Order.

        The form view uses name='cif_form_mail'. We keep this as a stable entry point and
        route through the existing wizard (`send.form.wizard`) that collects customer type
        (individual/company) and purchasers_count.
        """
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Select Customer Type'),
            'res_model': 'send.form.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_form_type': 'cif',
                'active_id': self.id,
                'active_model': 'sale.order',
            }
        }

    # =========================================================
    # CIF collection state helpers (backend)
    # =========================================================

    def action_start_cif_collection(self):
        """Mark the sale order as being in CIF collection.

        This is a lightweight helper used by the CIF send wizard and should never block
        the send action. It only moves the order into the intermediate `in_cif` state.
        """
        for order in self:
            if order.state not in ('cancel', 'done'):
                order.state = 'in_cif'
        return True


    def create_invoices_from_lines(self):
        allowed_states = ('sale', 'in_cif', 'in_eoi', 'booking_sent', 'booking_signed', 'spa_sent', 'spa_signed')
        for order in self:
            if order.state not in allowed_states:
                raise UserError("An invoice can be created after the Sale Order is confirmed.")
            for line in order.installment_line_ids:
                line.get_installment_invoice()
        return True
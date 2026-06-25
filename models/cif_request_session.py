# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from datetime import timedelta

import base64
import uuid
import logging

_logger = logging.getLogger(__name__)


class CIFRequestSession(models.Model):
    _name = 'cif.request.session'
    _description = 'CIF Request Session'
    _inherit = ['mail.thread']
    _order = 'create_date desc'

    sale_order_id = fields.Many2one('sale.order', required=True, ondelete='cascade', index=True)

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default='New', tracking=True)
    customer_type = fields.Selection(
        string='Customer Type',
        selection=[('person', 'Individual'), ('company', 'Company')]
    )
    cif_token = fields.Char(
        string='CIF Token',
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: base64.urlsafe_b64encode(uuid.uuid4().bytes).decode().removesuffix('=='),
        tracking=True,
    )

    # Quota tracking
    allowed_submissions = fields.Integer(string='Allowed Submissions', required=True, default=1, tracking=True)
    submitted_count = fields.Integer(string='Submitted Count', default=0, readonly=True, tracking=True)

    state = fields.Selection([
        ('active', 'Active'),
        ('expired', 'Expired'),
    ], default='active', tracking=True)

    # Optional time-bound expiry (not enforced yet; kept for future hardening)
    expires_at = fields.Datetime(string='Expires At', tracking=True)

    cif_form_ids = fields.One2many(
        'cif.form',
        'cif_request_session_id',
        string='CIF Forms',
        readonly=True,
    )

    cif_form_count = fields.Integer(
        string='CIF Forms Count',
        compute='_compute_cif_form_count',
        store=False,
    )

    email_sent_to = fields.Char(
        string='Email Sent To',
        help='Email addresses to whom CIF form was sent',
        copy=False,
    )
    email_sent_cc = fields.Char(
        string='Email CC',
        help='Email addresses who received CIF form as CC',
        copy=False,
    )


    @api.depends('cif_form_ids')
    def _compute_cif_form_count(self):
        for rec in self:
            rec.cif_form_count = len(rec.cif_form_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('cif.request.session.sequence') or 'New'
        return super().create(vals_list)

    def _check_active_and_quota(self):
        self.ensure_one()
        if self.state != 'active':
            raise ValidationError(_("CIF access link expired."))
        if (self.allowed_submissions or 0) <= (self.submitted_count or 0):
            raise ValidationError(_("CIF access link expired."))
        # Optional: enforce expires_at if configured
        if self.expires_at and fields.Datetime.now() > self.expires_at:
            raise ValidationError(_("CIF access link expired."))

    def consume_submission_slot(self):
        """Atomically consume 1 submission slot.

        Uses SELECT ... FOR UPDATE to avoid concurrent double-consumption.
        """
        self.ensure_one()
        self.env.cr.execute(
            "SELECT id, allowed_submissions, submitted_count, state FROM cif_request_session WHERE id = %s FOR UPDATE",
            [self.id],
        )
        row = self.env.cr.fetchone()
        if not row:
            raise ValidationError(_("CIF session not found."))
        _id, allowed, submitted, state = row
        if state != 'active' or allowed <= submitted:
            raise ValidationError(_("CIF access link expired."))

        new_submitted = submitted + 1
        new_state = 'expired' if new_submitted >= allowed else 'active'
        self.write({'submitted_count': new_submitted, 'state': new_state})
        return True


# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from .utils import PAYMENT_TYPE_OPTIONS


class ResPartner(models.Model):
    """Extend res.partner with CIF-related fields."""

    _inherit = 'res.partner'

    # CIF form count smart button
    cif_form_count = fields.Integer(
        string='CIF Forms',
        compute='_compute_cif_form_count',
        store=False,
    )

    # Agent/Agency fields
    agent_code = fields.Char(
        string='Agent ID',
        copy=False,
        help="Unique identifier for RE Agency agents"
    )
    representative = fields.Many2one('res.partner', string="Representative")
    is_re_agency = fields.Boolean(string="RE Agency")
    trade_license_no = fields.Char(string='Trade License Number')

    # Identity document fields
    passport_no = fields.Char('Passport Number')
    passport_supporting_docs = fields.Many2many(
        'ir.attachment',
        'res_partner_passport_docs_rel',
        'res_partner_id',
        'attachment_id',
        string='Passport Supporting Documents'
    )
    national_id_no = fields.Char('National ID Number')
    supporting_document_ids = fields.Many2many(
        'ir.attachment',
        'res_partner_supporting_docs_rel',
        'res_partner_id',
        'attachment_id',
        string='Supporting Documents'
    )
    nationality = fields.Many2one('res.country', string="Nationality")

    # Name fields
    middle_name = fields.Char(string='Middle Name')

    # Contact fields
    email_address = fields.Char(string='Alt. Email')
    date_of_birth = fields.Date(string='Date of Birth')
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other')
    ], string='Gender')
    source_of_income = fields.Char(string='Source of Income')

    # Payment/residency fields
    payment_type = fields.Selection(PAYMENT_TYPE_OPTIONS, string='Preferred Payment Type')
    residency_status = fields.Selection([
        ('resident', 'Resident'),
        ('non_resident', 'Non Resident')
    ], string='Residency Status')

    # Signature
    signature = fields.Binary(string="Signature", attachment=True)

    # Security questions
    security_answer_ids = fields.One2many(
        'security.question.answer',
        'partner_id',
        string='Security Questions & Answers',
    )

    shareholder_name = fields.Char(string='Shareholder Name')

    @api.depends('user_id')
    def _compute_cif_form_count(self):
        for partner in self:
            partner.cif_form_count = self.env['cif.form'].search_count([
                ('created_partner_id', '=', partner.id)
            ])

    def action_view_cif_forms(self):
        """Open CIF forms linked to this partner via smart button."""
        self.ensure_one()
        cif_forms = self.env['cif.form'].search([
            ('created_partner_id', '=', self.id)
        ])

        if not cif_forms:
            raise UserError(_("No CIF forms found for this partner."))

        if len(cif_forms) == 1:
            return {
                'name': _('Client Information Form'),
                'type': 'ir.actions.act_window',
                'res_model': 'cif.form',
                'view_mode': 'form',
                'res_id': cif_forms.id,
                'target': 'current',
            }

        return {
            'name': _('Client Information Forms'),
            'type': 'ir.actions.act_window',
            'res_model': 'cif.form',
            'view_mode': 'list,form',
            'domain': [('created_partner_id', '=', self.id)],
            'target': 'current',
        }
